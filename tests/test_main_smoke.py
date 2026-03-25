import importlib
import unittest


class MainSmokeTest(unittest.TestCase):
    def test_main_module_imports(self):
        module = importlib.import_module("main")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()

