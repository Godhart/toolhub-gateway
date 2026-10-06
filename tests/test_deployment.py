import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DeploymentTests(unittest.TestCase):
    def run_deploy(self, existing=False, fail=False):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            shutil.copy(ROOT / "deploy.sh", p / "deploy.sh")
            (p / ".env").write_text("DOMAIN=tools.test.net\nEMAIL=me@test.net\nTOOLHUB_UPSTREAM=router:3000\nTOOLHUB_CONTAINER=\n")
            if existing:
                cert = p / "data/letsencrypt/live/tools.test.net"
                cert.mkdir(parents=True)
                (cert / "fullchain.pem").write_text("cert")
                (cert / "privkey.pem").write_text("key")
            fake = p / "bin"
            fake.mkdir()
            (fake / "docker").write_text("#!/bin/sh\nprintf '%s | %s\\n' \"${NGINX_MODE:-default}\" \"$*\" >> \"$CALL_LOG\"\ncase \"$*\" in 'compose run --rm certbot init') exit \"${FAIL_INIT:-0}\" ;; esac\n")
            (fake / "docker").chmod(0o755)
            log = p / "calls"
            env = dict(os.environ, PATH=str(fake) + os.pathsep + os.environ["PATH"], CALL_LOG=str(log), FAIL_INIT="1" if fail else "0")
            result = subprocess.run(["sh", str(p / "deploy.sh")], env=env, capture_output=True, text=True)
            return result, log.read_text()

    def test_first_issuance_precedes_https_and_renewal(self):
        result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http | compose up -d nginx", calls)
        self.assertLess(calls.index("compose run --rm certbot init"), calls.index("https | compose up -d --force-recreate nginx"))
        self.assertLess(calls.index("compose exec -T nginx nginx -t"), calls.index("compose up -d certbot"))

    def test_existing_certificate_keeps_https(self):
        result, calls = self.run_deploy(existing=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("http |", calls)
        self.assertIn("https | compose up -d nginx", calls)

    def test_failed_issuance_does_not_enable_https_or_scheduler(self):
        result, calls = self.run_deploy(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("--force-recreate nginx", calls)
        self.assertNotIn("compose up -d certbot", calls)

    def test_shell_scripts_parse(self):
        for script in ROOT.rglob("*.sh"):
            subprocess.run(["sh", "-n", str(script)], check=True)

if __name__ == "__main__":
    unittest.main()
