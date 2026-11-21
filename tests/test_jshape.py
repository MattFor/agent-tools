import json
import os
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'jshape')
DOC = {
	'meta': {'count': 2, 'source': 'x' * 100},
	'items': [
		{'id': 1, 'name': 'a', 'tags': ['p', 'q']},
		{'id': 2, 'name': 'b', 'extra': None},
	],
	'odd key': True,
}


class Jshape(unittest.TestCase):
	def setUp(self):
		fd, self.path = tempfile.mkstemp(suffix='.json')
		with os.fdopen(fd, 'w') as f:
			json.dump(DOC, f)

	def run_jshape(self, *args, stdin=None):
		return subprocess.run([sys.executable, BIN, *args], check=False, input=stdin, capture_output=True, text=True)

	def test_shape(self):
		r = self.run_jshape(self.path)
		self.assertEqual(r.returncode, 0, r.stderr)
		lines = r.stdout.splitlines()
		self.assertEqual(lines[0], '. object keys=meta,items,odd key')
		self.assertIn('.items array len=2', lines)
		self.assertIn('.items[] object keys=id,name,tags?,extra?', lines)
		self.assertIn('.items[].id int  e.g. 1, 2', lines)
		self.assertIn('.items[].tags[] str  e.g. "p", "q"', lines)
		self.assertIn('.["odd key"] bool  e.g. true', lines)
		self.assertIn('.meta.source str  e.g. "' + 'x' * 60 + '…"', lines)

	def test_depth_and_samples(self):
		lines = self.run_jshape(self.path, '-d', '1', '-n', '1').stdout.splitlines()
		self.assertIn('.items array len=2', lines)
		self.assertFalse([x for x in lines if x.startswith('.items[]')])
		lines = self.run_jshape(self.path, '-n', '1').stdout.splitlines()
		self.assertIn('.items[].id int  e.g. 1', lines)

	def test_jsonl_from_stdin(self):
		r = self.run_jshape('-', stdin='{"x": 1}\n\n{"x": 2, "y": [1, 2, 3]}\n')
		lines = r.stdout.splitlines()
		self.assertTrue(lines[0].startswith('. array len=2'), lines[0])
		self.assertIn('JSON Lines', lines[0])
		self.assertIn('.[] object keys=x,y?', lines)
		self.assertIn('.[].y array len=3', lines)

	def test_paths(self):
		r = self.run_jshape('--paths', self.path)
		self.assertIn('.items[0].tags[1] = "q"', r.stdout.splitlines())
		self.assertIn('.items[1].extra = null', r.stdout.splitlines())
		self.assertIn('.["odd key"] = true', r.stdout.splitlines())

	def test_bad_input(self):
		r = self.run_jshape('-', stdin='{nope')
		self.assertNotEqual(r.returncode, 0)
		self.assertIn('not JSON', r.stderr)


if __name__ == '__main__':
	unittest.main()
