import os
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'subst')


def block(old, new, path=''):
	return f'{path}\n<<<<<<< SEARCH\n{old}\n=======\n{new}\n>>>>>>> REPLACE\n'


class Subst(unittest.TestCase):
	def setUp(self):
		self.d = tempfile.mkdtemp()
		self.a = os.path.join(self.d, 'a.txt')
		self.b = os.path.join(self.d, 'b.txt')
		for p, t in ((self.a, 'one\n\ttwo\nthree\n'), (self.b, 'x\nx\ny\n')):
			with open(p, 'w', newline='') as f:
				f.write(t)

	def run_subst(self, stdin, *args):
		return subprocess.run([sys.executable, BIN, *args], check=False, input=stdin, capture_output=True, text=True)

	def read(self, p):
		with open(p, newline='') as f:
			return f.read()

	def test_replace_once(self):
		r = self.run_subst(block('\ttwo', '\t2'), self.a)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(self.read(self.a), 'one\n\t2\nthree\n')

	def test_multi_file_and_atomic(self):
		ok = self.run_subst(block('one', '1', self.a) + block('y', 'z', self.b))
		self.assertEqual(ok.returncode, 0, ok.stderr)
		self.assertEqual(self.read(self.b), 'x\nx\nz\n')
		bad = self.run_subst(block('three', '3', self.a) + block('missing', 'q', self.b))
		self.assertNotEqual(bad.returncode, 0)
		self.assertIn('nothing written', bad.stderr)
		self.assertEqual(self.read(self.a), '1\n\ttwo\nthree\n')

	def test_ambiguous_and_all(self):
		r = self.run_subst(block('x', 'w'), self.b)
		self.assertIn('found 2 times', r.stderr)
		r = self.run_subst(block('x', 'w'), '-a', self.b)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(self.read(self.b), 'w\nw\ny\n')

	def test_whitespace_hint(self):
		r = self.run_subst(block('    two', '2'), self.a)
		self.assertIn('whitespace is ignored', r.stderr)

	def test_crlf_and_mode_and_symlink(self):
		with open(self.a, 'w', newline='') as f:
			f.write('p\r\nq\r\n')
		os.chmod(self.a, 0o755)
		link = os.path.join(self.d, 'link')
		os.symlink(self.a, link)
		r = self.run_subst(block('p\nq', 'r\ns'), link)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertTrue(os.path.islink(link))
		self.assertEqual(self.read(self.a), 'r\r\ns\r\n')
		self.assertEqual(os.stat(self.a).st_mode & 0o777, 0o755)

	def test_part_of_a_line(self):
		r = self.run_subst(block('hre', 'HRE'), self.a)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(self.read(self.a), 'one\n\ttwo\ntHREe\n')

	def test_dry_run(self):
		r = self.run_subst(block('one', '1'), '-n', self.a)
		self.assertIn('+1', r.stdout)
		self.assertEqual(self.read(self.a), 'one\n\ttwo\nthree\n')

	def test_stray_line_with_default_file(self):
		r = self.run_subst('fix the first word\n' + block('one', '1'), self.a)
		self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
	unittest.main()
