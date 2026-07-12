"""End-to-end tests for security-check.sh against throwaway fixtures.

Runs under pytest or `python -m unittest discover -s scripts/tests`.
Never touches the real repo — every check is pointed at a scratch dir via
the TARGET_DIR env var the script reads.
"""
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import git, run, script, TempRepoCase  # noqa: E402

SCRIPT = script("security-check.sh")


def has(tool):
    return shutil.which(tool) is not None


def run_check(target_dir, *args):
    return subprocess.run(
        [SCRIPT, *args],
        cwd=target_dir,
        env={**os.environ, "TARGET_DIR": target_dir},
        capture_output=True,
        text=True,
    )


@unittest.skipUnless(has("gitleaks"), "gitleaks not on PATH")
class TestSecrets(TempRepoCase):
    def test_clean_repo_passes(self):
        repo = os.path.join(self.tmp, "clean")
        os.makedirs(repo)
        git(["init", "-b", "main", "."], repo)
        with open(os.path.join(repo, "README.md"), "w") as fh:
            fh.write("# clean\n")
        git(["add", "-A"], repo)
        git(["commit", "-m", "init"], repo)

        result = run_check(repo, "secrets")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(has("openssl"), "openssl not on PATH")
    def test_committed_secret_fails(self):
        repo = os.path.join(self.tmp, "dirty")
        os.makedirs(repo)
        git(["init", "-b", "main", "."], repo)
        # A real (but throwaway, freshly-generated, never used anywhere else)
        # RSA key so gitleaks' private-key rule fires unambiguously. Generated
        # at test time rather than hardcoded, so no key material ever lands in
        # this repo's own git history for gitleaks to (correctly) flag later.
        run(["openssl", "genrsa", "-out", os.path.join(repo, "id_rsa"), "512"])
        git(["add", "-A"], repo)
        git(["commit", "-m", "oops"], repo)

        result = run_check(repo, "secrets")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(has("shellcheck"), "shellcheck not on PATH")
class TestShell(TempRepoCase):
    def _repo_with_script(self, content):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, "scripts"))
        with open(os.path.join(repo, "scripts", "test.sh"), "w") as fh:
            fh.write(content)
        return repo

    def test_clean_script_passes(self):
        repo = self._repo_with_script('#!/usr/bin/env bash\necho "hi"\n')
        result = run_check(repo, "shell")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_warning_level_bug_fails_shellcheck(self):
        # SC2164 (warning severity): `cd` without an `|| exit` failure check.
        # Not SC2086/SC2015 (info severity) — the -S warning threshold in
        # check_shell exists precisely to *not* fail on those, since this
        # codebase's dense style triggers several of them intentionally.
        repo = self._repo_with_script('#!/usr/bin/env bash\ncd /nonexistent\necho hi\n')
        result = run_check(repo, "shell")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(has("actionlint"), "actionlint not on PATH")
class TestActions(TempRepoCase):
    def _repo_with_workflow(self, content):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".github", "workflows"))
        with open(os.path.join(repo, ".github", "workflows", "ci.yml"), "w") as fh:
            fh.write(content)
        return repo

    def test_valid_workflow_passes(self):
        repo = self._repo_with_workflow(
            "name: ci\n"
            "on: push\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo hi\n"
        )
        result = run_check(repo, "actions")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_workflow_fails(self):
        # References an undefined step output — actionlint's expression
        # checker catches this even though the YAML itself is well-formed.
        repo = self._repo_with_workflow(
            "name: ci\n"
            "on: push\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ${{ steps.does_not_exist.outputs.value }}\n"
        )
        result = run_check(repo, "actions")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
