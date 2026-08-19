# Release checklist

1. Confirm Nine Parchments is closed.
2. Run the source verification:

   ```powershell
   python .\permanent_manager.py --verify
   ```

3. Build the standalone manager:

   ```powershell
   python -m PyInstaller --noconfirm --clean --onefile `
     --name NineParchmentsNoFriendlyFire .\permanent_manager.py
   ```

4. Test the standalone manager without changing the game:

   ```powershell
   .\dist\NineParchmentsNoFriendlyFire.exe
   .\dist\NineParchmentsNoFriendlyFire.exe --verify
   ```

5. Create a GitHub Release and attach only:

   `dist\NineParchmentsNoFriendlyFire.exe`

6. Record the manager executable's SHA-256 in the release notes:

   ```powershell
   Get-FileHash .\dist\NineParchmentsNoFriendlyFire.exe -Algorithm SHA256
   ```

Never attach `nineparchments_64bit.exe`, its `.original` backup, or any other
Nine Parchments game file. The compiled manager contains only the mod's
patching logic and requires a user-owned supported Steam installation.
