import getpass
import os
import unittest

from ybox.env import Environ


class EnvTest(unittest.TestCase):
    def test_home_dirs(self) -> None:
        target_home = f"/home/{getpass.getuser()}"
        env = Environ()
        self.assertEqual(os.environ["HOME"], env.home)
        self.assertEqual(target_home, os.environ["TARGET_HOME"])
        self.assertEqual(target_home, env.target_home)


if __name__ == '__main__':
    unittest.main()
