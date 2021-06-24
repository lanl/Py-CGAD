from py_cgad.githubapp import Node


def test_root_node():
    root_node = Node()
    # Root node does not have a name
    assert root_node.name == ""
    # There should be no sha it is empty
    assert root_node.sha is None
    # Relative path should simply be .
    assert root_node.relative_path == "."
    # There should be no files in the root node
    assert len(root_node.files) == 0
    # There should be no miscellaneous content e.g. media image files
    assert len(root_node.miscellaneous) == 0
    # Check that there are no nodes within the root node
    assert len(root_node.nodes) == 0
    # Check that the root path exists
    assert root_node.exists("")
    assert root_node.exists("./")
    assert root_node.exists(".")
    # Get sha of root directory, should be None
    assert root_node.getSha(".") is None
    # Get the type of the root directory should be "dir"
    assert root_node.type(".") == "dir"
    assert root_node.type("") == "dir"
    assert root_node.type("./") == "dir"
    # Get the relative path of the current node
    assert root_node.path == "."
    # Get all the paths with file1
    assert len(root_node.getRelativePaths("file1")) == 0


def test_add_dir():
    root_node = Node()
    root_node.insert("bin", "dir", "316070e1e044c6f1b3659507bbbc3ad56524816a")
    assert root_node.exists("./bin")
    assert root_node.exists("bin")
    assert len(root_node.nodes) == 1
    assert root_node.type("bin") == "dir"
    assert len(root_node.getRelativePaths("bin")) == 1
    assert root_node.getRelativePaths("bin")[0] == "./bin"
    assert root_node.getSha("bin") == "316070e1e044c6f1b3659507bbbc3ad56524816a"

    root_node.insert("./bin2", "dir", "4444444444444444444444444444444444444444")
    assert root_node.exists("./bin2")
    assert root_node.exists("bin2")
    assert len(root_node.nodes) == 2
    assert root_node.type("bin2") == "dir"
    assert len(root_node.getRelativePaths("bin")) == 1
    assert len(root_node.getRelativePaths("bin2")) == 1
    assert root_node.getRelativePaths("bin2")[0] == "./bin2"
    assert root_node.getSha("bin2") == "4444444444444444444444444444444444444444"

    root_node.insert("bin/lib", "dir", "6666666666666666666666666666666666666666")
    assert root_node.exists("./bin/lib")
    assert root_node.exists("bin/lib")
    assert len(root_node.nodes) == 2
    assert root_node.type("bin/lib") == "dir"
    assert len(root_node.getRelativePaths("bin")) == 1
    assert len(root_node.getRelativePaths("bin2")) == 1
    assert len(root_node.getRelativePaths("bin/lib")) == 1
    assert root_node.getRelativePaths("bin/lib")[0] == "./bin/lib"
    assert root_node.getSha("bin/lib") == "6666666666666666666666666666666666666666"

    root_node.insert("bin2/lib", "dir", "8888888888888888888888888888888888888888")
    assert root_node.exists("./bin2/lib")
    assert root_node.exists("bin2/lib")
    assert len(root_node.nodes) == 2
    assert root_node.type("bin2/lib") == "dir"
    assert len(root_node.getRelativePaths("bin")) == 1
    assert len(root_node.getRelativePaths("bin2")) == 1
    assert len(root_node.getRelativePaths("bin/lib")) == 1
    assert len(root_node.getRelativePaths("bin2/lib")) == 1
    assert len(root_node.getRelativePaths("lib")) == 2
    assert root_node.getSha("bin2/lib") == "8888888888888888888888888888888888888888"
    rel_paths = root_node.getRelativePaths("lib")
    bin2_lib_found = False
    bin_lib_found = False
    for path in rel_paths:
        if path == "./bin/lib":
            bin_lib_found = True
        elif path == "./bin2/lib":
            bin2_lib_found = True
    assert bin_lib_found
    assert bin2_lib_found


def test_add_file():
    root_node = Node()
    root_node.insert("test.py", "file", "316070e1e044c6f1b3659507bbbc3ad56524816a")
    assert root_node.exists("./test.py")
    assert root_node.exists("test.py")
    assert len(root_node.nodes) == 0
    assert root_node.type("test.py") == "file"
    assert len(root_node.getRelativePaths("test.py")) == 1
    assert root_node.getRelativePaths("test.py")[0] == "./test.py"
    assert root_node.getSha("test.py") == "316070e1e044c6f1b3659507bbbc3ad56524816a"


def test_add_misc():
    root_node = Node()
    root_node.insert("test.png", "misc", "316070e1e044c6f1b3659507bbbc3ad56524816a")
    assert root_node.exists("./test.png")
    assert root_node.exists("test.png")
    assert len(root_node.nodes) == 0
    assert root_node.type("test.png") == "misc"
    assert len(root_node.getRelativePaths("test.png")) == 1
    assert root_node.getRelativePaths("test.png")[0] == "./test.png"
    assert root_node.getSha("test.png") == "316070e1e044c6f1b3659507bbbc3ad56524816a"


def test_add_file_to_dir():
    root_node = Node()
    root_node.insert("src", "dir", "8888888888888888888888888888888888888888")
    root_node.insert(
        "./src/test.py", "file", "316070e1e044c6f1b3659507bbbc3ad56524816a"
    )
    assert root_node.exists("./src/test.py")
    assert root_node.exists("src/test.py")
    assert len(root_node.nodes) == 1
    assert root_node.type("src/test.py") == "file"
    assert len(root_node.getRelativePaths("src/test.py")) == 1
    assert root_node.getRelativePaths("test.py")[0] == "./src/test.py"
    assert (
        root_node.getSha("./src/test.py") == "316070e1e044c6f1b3659507bbbc3ad56524816a"
    )
