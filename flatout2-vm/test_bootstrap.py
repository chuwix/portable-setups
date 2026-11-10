from pathlib import Path
import subprocess
import unittest


BOOTSTRAP = Path(__file__).with_name("bootstrap.sh")


class BootstrapTests(unittest.TestCase):
    def script(self, mocks: str, expected: int = 0) -> str:
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; ' + mocks, "bootstrap-test", str(BOOTSTRAP)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_supported_tools_are_not_modified(self) -> None:
        output = self.script('''
python_is_supported() { return 0; }
utm_is_supported() { return 0; }
brew() { echo "UNEXPECTED MUTATION"; return 1; }
ensure_prerequisites
''')
        self.assertNotIn("UNEXPECTED", output)

    def test_managed_homebrew_is_not_modified(self) -> None:
        output = self.script('''
python_is_supported() { return 0; }
utm_is_supported() { return 1; }
brew() {
  if [[ "$1" == --repository ]]; then
    echo /opt/homebrew/Library/.homebrew-is-managed-by-nix
  else
    echo UNEXPECTED
  fi
}
ensure_prerequisites
''', expected=1)
        self.assertIn("Nix-managed", output)
        self.assertNotIn("UNEXPECTED", output)

    def test_missing_utm_is_installed_and_rechecked(self) -> None:
        output = self.script('''
installed=0
python_is_supported() { return 0; }
utm_is_supported() { (( installed )); }
brew() {
  case "$*" in
    --repository) echo /opt/homebrew ;;
    'list --cask utm') return 1 ;;
    'install --cask utm') installed=1; echo installed-utm ;;
    *) return 1 ;;
  esac
}
ensure_prerequisites
''')
        self.assertIn("installed-utm", output)

    def test_old_utm_is_upgraded(self) -> None:
        output = self.script('''
installed=0
python_is_supported() { return 0; }
utm_is_supported() { (( installed )); }
brew() {
  case "$*" in
    --repository) echo /opt/homebrew ;;
    'list --cask utm') return 0 ;;
    'upgrade --cask utm') installed=1; echo upgraded-utm ;;
    *) return 1 ;;
  esac
}
ensure_prerequisites
''')
        self.assertIn("upgraded-utm", output)

    def test_failed_install_stops_setup(self) -> None:
        self.script('''
python_is_supported() { return 0; }
utm_is_supported() { return 1; }
brew() {
  [[ "$1" == --repository ]] && { echo /opt/homebrew; return 0; }
  return 1
}
ensure_prerequisites
''', expected=1)

    def test_python_install_uses_homebrew_interpreter(self) -> None:
        output = self.script('''
python_is_supported() { [[ "$1" == /opt/homebrew/opt/python/bin/python3 ]]; }
utm_is_supported() { return 0; }
brew() {
  case "$*" in
    --repository) echo /opt/homebrew ;;
    'install python') echo installed-python ;;
    '--prefix python') echo /opt/homebrew/opt/python ;;
    *) return 1 ;;
  esac
}
ensure_prerequisites || exit 1
echo "interpreter=$PYTHON"
''')
        self.assertIn("installed-python", output)
        self.assertIn("interpreter=/opt/homebrew/opt/python/bin/python3", output)


if __name__ == "__main__":
    unittest.main()
