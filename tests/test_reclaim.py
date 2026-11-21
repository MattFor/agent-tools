import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'reclaim')
K = 1024


def blob(path, size):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, 'wb') as f:
		# Random bytes: a compressing filesystem would shrink anything else.
		f.write(os.urandom(size))


class Reclaim(unittest.TestCase):
	def setUp(self):
		self.d = os.path.realpath(tempfile.mkdtemp())
		self.addCleanup(shutil.rmtree, self.d)
		p = self.p
		blob(p('proj/target/debug/big'), 300 * K)
		blob(p('proj/target/__pycache__/x.pyc'), 8 * K)
		blob(p('proj/.git/hooks/__pycache__/z.pyc'), 50 * K)
		open(p('proj/Cargo.toml'), 'w').close()
		blob(p('web/node_modules/pkg/index.js'), 100 * K)
		os.link(p('web/node_modules/pkg/index.js'), p('web/node_modules/pkg/copy.js'))
		open(p('web/package.json'), 'w').close()
		blob(p('env/lib/x'), 40 * K)
		open(p('env/pyvenv.cfg'), 'w').close()
		blob(p('lib/__pycache__/m.pyc'), 20 * K)
		blob(p('app/dist/bundle.js'), 60 * K)
		open(p('app/package.json'), 'w').close()
		blob(p('plain/build/x'), 100 * K)
		blob(p('core.123'), 100 * K)
		blob(p('.cache/foo/data'), 200 * K)
		blob(p('downloads/old.iso'), 300 * K)
		blob(p('downloads/new.iso'), 300 * K)
		month_ago = time.time() - 60 * 86400
		os.utime(p('downloads/old.iso'), (month_ago, month_ago))
		os.makedirs(p('loop'))
		os.symlink('.', p('loop/self'))
		os.symlink('..', p('loop/up'))
		os.symlink(p('proj/target'), p('loop/target'))

	def p(self, rel):
		return os.path.join(self.d, rel)

	def run_reclaim(self, *args, path=None):
		env = {**os.environ, 'HOME': self.d, 'PATH': path if path is not None else os.environ['PATH']}
		return subprocess.run(
			[sys.executable, BIN, *args], check=False, capture_output=True, text=True, env=env, timeout=60
		)

	def items(self, *args):
		r = self.run_reclaim(*args, '--json')
		self.assertEqual(r.returncode, 0, r.stderr)
		return json.loads(r.stdout)

	def test_classification(self):
		kinds = {os.path.relpath(i['path'], self.d): i['kind'] for i in self.items(self.d, '--min', '1K')}
		self.assertEqual(
			kinds,
			{
				'proj/target': 'rust-target',
				'web/node_modules': 'node-modules',
				'env': 'venv',
				'lib/__pycache__': 'pycache',
				'app/dist': 'dist',
				'core.123': 'core',
				'.cache/foo': 'cache',
				'downloads/old.iso': 'download',
			},
		)

	def test_sizes_sorted_hard_links_once_and_symlinks_ignored(self):
		items = self.items(self.d, '--min', '1K')
		sizes = [i['size'] for i in items]
		self.assertEqual(sizes, sorted(sizes, reverse=True))
		by = {os.path.relpath(i['path'], self.d): i for i in items}
		self.assertEqual(items[0]['path'], self.p('proj/target'))
		self.assertGreaterEqual(by['proj/target']['size'], 300 * K)
		# The target inside .git and the symlinks to the target never add to it.
		self.assertLess(by['proj/target']['size'], 340 * K)
		# Two names for one 100K file.
		self.assertGreaterEqual(by['web/node_modules']['size'], 100 * K)
		self.assertLess(by['web/node_modules']['size'], 150 * K)
		self.assertEqual(by['downloads/old.iso']['age_days'], 60)
		self.assertEqual(by['env']['hint'], 'rm -rf')
		self.assertEqual(by['proj/target']['hint'], 'cargo clean')

	def test_min_and_n(self):
		kinds = {i['kind'] for i in self.items(self.d, '--min', '250K')}
		self.assertEqual(kinds, {'rust-target', 'download'})
		self.assertEqual(len(self.items(self.d, '--min', '1K', '-n', '2')), 2)

	def test_older_applies_to_downloads(self):
		kinds = {i['kind'] for i in self.items(self.d, '--min', '250K', '--older', '90')}
		self.assertEqual(kinds, {'rust-target'})

	def test_rows_use_tilde_and_total(self):
		r = self.run_reclaim('--min', '250K', path='')
		self.assertEqual(r.returncode, 0, r.stderr)
		lines = r.stdout.splitlines()
		self.assertRegex(lines[0], r'^ *[\d.]+[KM]  +\d+d  rust-target +~/proj/target  \(cargo clean\)$')
		self.assertRegex(lines[1], r'~/downloads/old\.iso')
		self.assertRegex(lines[-1], r'^total [\d.]+[KM] in 2 items$')

	def test_footer_names_only_commands_that_exist(self):
		bin_dir = os.path.join(self.d, 'stubs')
		os.makedirs(bin_dir)
		with open(os.path.join(bin_dir, 'docker'), 'w') as f:
			f.write('#!/bin/sh\n')
		os.chmod(os.path.join(bin_dir, 'docker'), 0o755)
		r = self.run_reclaim('--min', '250K', path=bin_dir)
		self.assertEqual(r.stdout.splitlines()[-1], 'not measured here: docker system df')
		self.assertNotIn('not measured', self.run_reclaim('--min', '250K', path='').stdout)

	def test_usage_errors(self):
		self.assertEqual(self.run_reclaim(self.p('nope')).returncode, 2)
		self.assertEqual(self.run_reclaim('--min', 'lots').returncode, 2)


if __name__ == '__main__':
	unittest.main()
