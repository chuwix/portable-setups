# Finished playing?

Choose whether you want to keep the game for later or remove Windows and the game completely.
Nothing is removed automatically when you quit the game.

## Keep playing later

Save your game, exit FlatOut 2, then choose **Start → Power → Shut down** inside Windows.
Wait for UTM to show the VM as stopped. Closing its window is not a substitute for shutting
Windows down. Your installed game and saves stay in the VM for next time.

## Remove temporary game-installation media only

Use this after the guest helper reports a successful installation. If installation failed,
keep the media and logs until you have resolved the problem.

1. Shut down Windows normally and wait for UTM to show the VM as stopped.
2. Open Terminal in the repository's `flatout2-vm` directory and run:

   ```sh
   python3 flatout2_vm.py detach-game
   ```

   If you used a custom VM location, include the same `--home` argument:

   ```sh
   python3 flatout2_vm.py detach-game --home '/your/exact/VM-home'
   ```

3. Check the message confirming that the game CD was detached. The guest installation and
   saves are unchanged. If an unattached ISO is found instead, the command asks before moving
   it to a uniquely named backup; it does not delete unrecognized media.

The original USB/folder is never shared with Windows. Once the launcher says the local game
ISO was copied and verified, you may eject an external source drive in Finder. This is separate
from detaching the virtual game CD. Source installers are yours to keep.

## Remove the VM permanently

**Removing the VM deletes its Windows installation, installed games, accounts, and game saves.**
If you might return, make a backup before removing anything. This is not required after each
play session.

If you deliberately choose **permanent removal without backups**, all saves, Windows state,
repair archives, and runtime evidence will be lost. Skip backup creation only with that explicit
decision. Do not describe removed logs, screenshots, or VM copies as available evidence afterward;
retain only reviewed, sanitized findings. The project's current cleanup authorization and verified
completion status belong in [state.md](state.md), not this general procedure.

1. Save, exit the game, and shut down Windows normally. Wait for UTM to show it as stopped.
2. Identify the exact VM you created. In UTM, use its action menu to reveal the VM in Finder
   and verify the path. Do not identify it by name alone if several VMs have the same name.
   The default location created by these scripts is:

   ```text
   ~/Library/Application Support/FlatOut2VM/FlatOut 2 Sandbox.utm
   ```

   If you supplied `--home`, use that location instead. Development/test VM homes are separate;
   do not remove them merely because their names begin with `FlatOut2VM`.
3. To preserve your game and saves, copy the **entire stopped VM home** to a safe location,
   or use UTM's export action for the complete VM and separately preserve the home-side files
   you need. A configuration-only copy does not contain Windows or saves. Keep backups private:
   the VM and its home-side `credentials.json` contain account data. Verify the complete backup
   exists before continuing, unless you explicitly chose no-backup permanent removal above.
   Keep a full VM backup if you want a self-contained way to restore
   saves without enabling host folder sharing.
4. Remove the selected VM from UTM using its action menu. Read the confirmation carefully:
   depending on where the VM is stored, UTM can remove its data as well as its list entry.
   Do not choose this until any wanted backup is complete or you have explicitly accepted its loss.
5. In Finder, inspect the **exact VM home you verified**, then move remaining setup-owned files
   to the Trash. These include the VM bundle if UTM left it behind, `seed`, `credentials.json`,
   `vm-id`, and any installer-media or diagnostic backups inside that home. Preserve any unrelated
   files you put there. Do not delete the parent `Application Support` directory.
6. Optionally remove cached downloads from this setup's cache folder:

   ```text
   ~/Library/Caches/portable-setups/flatout2-vm/
   ```

   If you supplied `--cache`, inspect that location instead. Keep the cache if another FlatOut 2
   VM setup will reuse it. Do not remove other `portable-setups` caches or purchased installers.
7. Check that UTM no longer lists the removed VM and that no wanted files are in the Trash.
   Empty the Trash only when you are certain you no longer need them. Backups retained elsewhere
   still occupy space; keep or remove those separately.

Leave Homebrew, Python, UTM, and other shared tools installed unless you separately decide
that no other application or VM needs them. You may remove the downloaded repository copy
once you no longer need its launchers or instructions.

If a repair reported an archive such as `C:\Games\FlatOut2-saves-<GUID>\Savegame`, that archive
is inside Windows too. Preserve it with the stopped VM before permanent removal. A repair
archive is not a separate backup and will be lost if the VM is deleted.

### Host-wide audio settings

If you explicitly changed **UTM → Settings → Sound → Sound Backend** for this setup, consider
restoring its previous value after removing the VM. This preference affects other QEMU VMs,
so do not change it blindly. A VM kept with an HDA sound card can expose recording hardware
on a later launch if the backend is changed from CoreAudio to Default or SPICE. Remove that
test card while stopped before reverting the backend if you intend to keep the VM output-only.

See [UTM's action-menu documentation](https://docs.getutm.app/basics/actions/) for its reveal,
export, copy, and remove actions. No removal command is run by this guide or by normal Play.
