#!/usr/bin/env python3
"""Install/remove the proven permanent Nine Parchments no-friendly-fire hook."""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import struct
import sys
import tempfile

VENDOR = pathlib.Path(__file__).resolve().parent / "vendor"
sys.path.insert(0, str(VENDOR))

import pefile  # type: ignore  # noqa: E402


ORIGINAL_SHA256 = "69b1c5e94533858e7403049f95070c3b2494d5d871e910fcb92ec5c3a217ca27"
LEGACY_HEALTH_ONLY_SHA256 = "8e3d7ffb69b6c938793ea6a33b1ccd6bbc23079f7951fbe0a72ecff8ef7baeaf"
ORIGINAL_LENGTH = 0x3656C00
IMAGE_BASE = 0x140000000
HANDLER_VA = 0x1410E8F20
HANDLER_FILE_OFFSET = 0x10E8520
HANDLER_ORIGINAL = bytes.fromhex("48 89 5c 24 08")
PRESENTATION_VA = 0x140353300
PRESENTATION_FILE_OFFSET = 0x352900
PRESENTATION_ORIGINAL = bytes.fromhex("48 8b c4 55 41")
SECTION_HEADER_OFFSET = 0x430
SECTION_RVA = 0x3A9D000
SECTION_VA = IMAGE_BASE + SECTION_RVA
SECTION_RAW_OFFSET = ORIGINAL_LENGTH
SECTION_RAW_SIZE = 0x200
PRESENTATION_CAVE_OFFSET = 0xC0
NEW_SIZE_OF_IMAGE = 0x3A9E000
PLAYER_COMPONENT_TYPE_VA = 0x140B6D520
GET_GAME_STATE_VA = 0x1400C7EF0
RESOLVE_ENTITY_VA = 0x140BBC760


class Assembler:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    @property
    def address(self) -> int:
        return self.origin + len(self.code)

    def emit(self, data: bytes) -> None:
        self.code += data

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def jcc(self, opcode: bytes, label: str) -> None:
        self.emit(opcode)
        self.fixups.append((len(self.code), label))
        self.emit(bytes(4))

    def call(self, target: int) -> None:
        next_address = self.address + 5
        self.emit(b"\xe8" + struct.pack("<i", target - next_address))

    def jump(self, target: int) -> None:
        next_address = self.address + 5
        self.emit(b"\xe9" + struct.pack("<i", target - next_address))

    def finish(self) -> bytes:
        for displacement_at, label in self.fixups:
            displacement = self.labels[label] - (displacement_at + 4)
            struct.pack_into("<i", self.code, displacement_at, displacement)
        return bytes(self.code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_health_cave() -> bytes:
    asm = Assembler(SECTION_VA)
    asm.emit(bytes.fromhex("48 83 ec 68"))
    asm.emit(bytes.fromhex("48 89 4c 24 20 48 89 54 24 28"))
    asm.emit(bytes.fromhex("48 8b 81 e8 00 00 00 48 89 44 24 30 48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Target entity must have PlayerComponent.
    asm.call(PLAYER_COMPONENT_TYPE_VA)
    asm.emit(bytes.fromhex("48 8b d0 48 8b 4c 24 30 48 8b 01 ff 90 b8 02 00 00"))
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Resolve the source entity from the event's source ID.
    asm.emit(bytes.fromhex("48 8b 4c 24 20"))
    asm.call(GET_GAME_STATE_VA)
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")
    asm.emit(bytes.fromhex("48 8b 48 38 48 8b 44 24 28 8b 50 1c"))
    asm.call(RESOLVE_ENTITY_VA)
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")
    asm.emit(bytes.fromhex("48 89 44 24 38 48 3b 44 24 30"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")  # self-damage remains enabled

    # Source entity must also have PlayerComponent.
    asm.call(PLAYER_COMPONENT_TYPE_VA)
    asm.emit(bytes.fromhex("48 8b d0 48 8b 4c 24 38 48 8b 01 ff 90 b8 02 00 00"))
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Distinct player entities: keep hit visuals, skip health subtraction.
    asm.emit(bytes.fromhex("48 83 c4 68 c3"))

    asm.label("continue")
    asm.emit(bytes.fromhex("48 8b 4c 24 20 48 8b 54 24 28 48 83 c4 68"))
    asm.emit(HANDLER_ORIGINAL)
    asm.jump(HANDLER_VA + len(HANDLER_ORIGINAL))
    return asm.finish()


def build_presentation_cave() -> bytes:
    asm = Assembler(SECTION_VA + PRESENTATION_CAVE_OFFSET)
    asm.emit(bytes.fromhex("48 83 ec 68"))
    asm.emit(bytes.fromhex("48 89 4c 24 20 48 89 54 24 28"))
    asm.emit(bytes.fromhex("48 8b 81 e8 00 00 00 48 89 44 24 30 48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Target entity must have PlayerComponent.
    asm.call(PLAYER_COMPONENT_TYPE_VA)
    asm.emit(bytes.fromhex("48 8b d0 48 8b 4c 24 30 48 8b 01 ff 90 b8 02 00 00"))
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Resolve the true source ID from the compact pre-health hit record at +0x0c.
    asm.emit(bytes.fromhex("48 8b 4c 24 20"))
    asm.call(GET_GAME_STATE_VA)
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")
    asm.emit(bytes.fromhex("48 8b 48 38 48 8b 44 24 28 8b 50 0c"))
    asm.call(RESOLVE_ENTITY_VA)
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")
    asm.emit(bytes.fromhex("48 89 44 24 38 48 3b 44 24 30"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Source entity must also have PlayerComponent.
    asm.call(PLAYER_COMPONENT_TYPE_VA)
    asm.emit(bytes.fromhex("48 8b d0 48 8b 4c 24 38 48 8b 01 ff 90 b8 02 00 00"))
    asm.emit(bytes.fromhex("48 85 c0"))
    asm.jcc(bytes.fromhex("0f 84"), "continue")

    # Distinct player entities: skip reaction, floating text, and health dispatch.
    asm.emit(bytes.fromhex("48 83 c4 68 c3"))

    asm.label("continue")
    asm.emit(bytes.fromhex("48 8b 4c 24 20 48 8b 54 24 28 48 83 c4 68"))
    asm.emit(PRESENTATION_ORIGINAL)
    asm.jump(PRESENTATION_VA + len(PRESENTATION_ORIGINAL))
    return asm.finish()


def patch_original(original: bytes) -> bytes:
    if digest(original) != ORIGINAL_SHA256 or len(original) != ORIGINAL_LENGTH:
        raise RuntimeError("input is not the supported original Steam executable")
    result = bytearray(original)
    if bytes(result[HANDLER_FILE_OFFSET : HANDLER_FILE_OFFSET + 5]) != HANDLER_ORIGINAL:
        raise RuntimeError("unexpected health-handler bytes")
    if bytes(
        result[PRESENTATION_FILE_OFFSET : PRESENTATION_FILE_OFFSET + 5]
    ) != PRESENTATION_ORIGINAL:
        raise RuntimeError("unexpected presentation-handler bytes")

    health_cave = build_health_cave()
    presentation_cave = build_presentation_cave()
    cave_size = PRESENTATION_CAVE_OFFSET + len(presentation_cave)
    if len(health_cave) > PRESENTATION_CAVE_OFFSET or cave_size > SECTION_RAW_SIZE:
        raise RuntimeError("hook code no longer fits its section")
    hook_next = HANDLER_VA + 5
    result[HANDLER_FILE_OFFSET : HANDLER_FILE_OFFSET + 5] = (
        b"\xe9" + struct.pack("<i", SECTION_VA - hook_next)
    )
    presentation_hook_next = PRESENTATION_VA + 5
    result[PRESENTATION_FILE_OFFSET : PRESENTATION_FILE_OFFSET + 5] = (
        b"\xe9"
        + struct.pack(
            "<i",
            SECTION_VA + PRESENTATION_CAVE_OFFSET - presentation_hook_next,
        )
    )

    e_lfanew = struct.unpack_from("<I", result, 0x3C)[0]
    file_header = e_lfanew + 4
    optional_header = file_header + 20
    if struct.unpack_from("<H", result, optional_header)[0] != 0x20B:
        raise RuntimeError("expected a PE32+ executable")
    if struct.unpack_from("<H", result, file_header + 2)[0] != 10:
        raise RuntimeError("unexpected original section count")
    struct.pack_into("<H", result, file_header + 2, 11)
    struct.pack_into("<I", result, optional_header + 56, NEW_SIZE_OF_IMAGE)
    struct.pack_into("<I", result, optional_header + 64, 0)

    section_header = struct.pack(
        "<8sIIIIIIHHI",
        b".npff\0\0\0",
        cave_size,
        SECTION_RVA,
        SECTION_RAW_SIZE,
        SECTION_RAW_OFFSET,
        0,
        0,
        0,
        0,
        0x60000020,
    )
    result[SECTION_HEADER_OFFSET : SECTION_HEADER_OFFSET + 40] = section_header
    cave = bytearray(SECTION_RAW_SIZE)
    cave[: len(health_cave)] = health_cave
    cave[
        PRESENTATION_CAVE_OFFSET : PRESENTATION_CAVE_OFFSET + len(presentation_cave)
    ] = presentation_cave
    result.extend(cave)

    parsed = pefile.PE(data=bytes(result), fast_load=True)
    struct.pack_into("<I", result, optional_header + 64, parsed.generate_checksum())
    return bytes(result)


def paths() -> tuple[pathlib.Path, pathlib.Path]:
    manager_directory = (
        pathlib.Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else pathlib.Path(__file__).resolve().parent
    )
    for root in (
        manager_directory,
        manager_directory.parent,
        manager_directory.parent.parent,
    ):
        executable = root / "nineparchments_64bit.exe"
        if executable.exists():
            return executable, root / "nineparchments_64bit.exe.np-no-ff.original"
    raise RuntimeError(
        "nineparchments_64bit.exe was not found beside the manager or in its "
        "parent folder; place the manager in the Nine Parchments game folder "
        "or a direct subfolder"
    )


def read_backup(backup: pathlib.Path) -> bytes:
    data = backup.read_bytes()
    if digest(data) != ORIGINAL_SHA256:
        raise RuntimeError("the original backup failed hash verification")
    return data


def atomic_write(path: pathlib.Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def expected_hash(original: bytes) -> str:
    return digest(patch_original(original))


def status() -> int:
    executable, backup = paths()
    current = executable.read_bytes()
    current_hash = digest(current)
    original = read_backup(backup)
    if current_hash == ORIGINAL_SHA256:
        state = "not installed (original executable)"
    elif current_hash == LEGACY_HEALTH_ONLY_SHA256:
        state = "legacy health-only build installed (upgrade available)"
    elif current_hash == expected_hash(original):
        state = "installed"
    else:
        state = "unknown build; no changes will be made"
    print(f"Status: {state}")
    print(f"Executable SHA-256: {current_hash}")
    print(f"Permanent patched SHA-256: {expected_hash(original)}")
    return 0


def verify() -> int:
    _, backup = paths()
    original = read_backup(backup)
    patched = patch_original(original)
    parsed = pefile.PE(data=patched, fast_load=True)
    section = parsed.sections[-1]
    if section.Name.rstrip(b"\0") != b".npff":
        raise RuntimeError("generated section was not parsed correctly")
    if parsed.FILE_HEADER.NumberOfSections != 11:
        raise RuntimeError("generated PE has an incorrect section count")
    if parsed.OPTIONAL_HEADER.SizeOfImage != NEW_SIZE_OF_IMAGE:
        raise RuntimeError("generated PE has an incorrect image size")
    print(f"Verified permanent build: {digest(patched)}")
    print(
        f"Health hook size: {len(build_health_cave()):#x}; "
        f"presentation hook size: {len(build_presentation_cave()):#x}; "
        f"section raw size: {SECTION_RAW_SIZE:#x}"
    )
    return 0


def install() -> int:
    executable, backup = paths()
    current = executable.read_bytes()
    current_hash = digest(current)
    if current_hash != ORIGINAL_SHA256:
        original = read_backup(backup)
        if current_hash == expected_hash(original):
            print("Permanent no-friendly-fire mod is already installed.")
            return 0
        if current_hash != LEGACY_HEALTH_ONLY_SHA256:
            raise RuntimeError("executable is not the supported original or legacy build")
        patched = patch_original(original)
        atomic_write(executable, patched)
        if digest(executable.read_bytes()) != digest(patched):
            raise RuntimeError("post-upgrade verification failed")
        print("Upgraded permanent mod with PVP presentation suppression.")
        print(f"Patched SHA-256: {digest(patched)}")
        return 0
    if not backup.exists():
        shutil.copy2(executable, backup)
    original = read_backup(backup)
    patched = patch_original(original)
    atomic_write(executable, patched)
    if digest(executable.read_bytes()) != digest(patched):
        raise RuntimeError("post-install verification failed")
    print("Installed permanent Nine Parchments No Friendly Fire mod.")
    print(f"Patched SHA-256: {digest(patched)}")
    return 0


def uninstall() -> int:
    executable, backup = paths()
    original = read_backup(backup)
    current_hash = digest(executable.read_bytes())
    if current_hash == ORIGINAL_SHA256:
        print("Mod is not installed; executable is already original.")
        return 0
    if current_hash not in (expected_hash(original), LEGACY_HEALTH_ONLY_SHA256):
        raise RuntimeError("current executable is not the expected permanent build")
    atomic_write(executable, original)
    if digest(executable.read_bytes()) != ORIGINAL_SHA256:
        raise RuntimeError("post-uninstall verification failed")
    print("Removed permanent mod; original executable restored.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--install", action="store_true")
    actions.add_argument("--uninstall", action="store_true")
    actions.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.install:
        return install()
    if args.uninstall:
        return uninstall()
    if args.verify:
        return verify()
    return status()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, struct.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
