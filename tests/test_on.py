import os
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'on')


class On(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.d = tempfile.mkdtemp()
		# Fake remotes: the prefix runs the command locally with HOME pointing at a folder per host.
		cls.hosts = os.path.join(cls.d, 'hosts')
		with open(cls.hosts, 'w') as f:
			for name in ('alpha,a', 'beta'):
				home = os.path.join(cls.d, name.split(',')[0])
				os.makedirs(home)
				f.write(f'{name}  HOME={home} sh -c\n')
			f.write('down  sh -c "exit 255"\n')

	def on(self, *args, stdin=None):
		env = {**os.environ, 'ON_HOSTS': self.hosts}
		return subprocess.run(
			[sys.executable, BIN, *args], input=stdin, capture_output=True, text=True, env=env, check=False
		)

	def test_run_exit_code_and_stdin(self):
		r = self.on('a', 'echo $HOME; cat; exit 3', stdin='piped\n')
		self.assertEqual(r.returncode, 3)
		self.assertIn('alpha', r.stdout)
		self.assertIn('piped', r.stdout)

	def test_put_and_get(self):
		src = os.path.join(self.d, 'file.txt')
		with open(src, 'w') as f:
			f.write('data\n')
		r = self.on('alpha', 'put', src, '~/in')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('same as local', r.stdout)
		out = os.path.join(self.d, 'back')
		r = self.on('alpha', 'get', '~/in/file.txt', out)
		self.assertEqual(r.returncode, 0, r.stderr)
		with open(os.path.join(out, 'file.txt')) as f:
			self.assertEqual(f.read(), 'data\n')

	def test_many_prefixes_and_unreachable(self):
		r = self.on('alpha,beta,down', 'echo hi')
		self.assertIn('alpha: hi', r.stdout)
		self.assertIn('beta: hi', r.stdout)
		self.assertIn('down: unreachable', r.stdout)
		self.assertEqual(r.returncode, 255)

	def test_timeout_and_unknown(self):
		self.assertEqual(self.on('beta', '-t', '0.5', 'sleep 5').returncode, 124)
		self.assertIn('unknown host', self.on('nope', 'true').stderr)


if __name__ == '__main__':
	unittest.main()
