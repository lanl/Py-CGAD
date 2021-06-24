#!/usr/bin/env python3

import copy
import os
import logging
import datetime
import filecmp
import pathlib
import json
import shutil
import base64
from io import BytesIO
import jwt
import pem
import pycurl
import re
from git import Repo
import git

# Checks to ensure a url is valid
def urlIsValid(candidate_url):
    # Regex to check valid URL
    regex = (
        "((http|https)://)(www.)?"
        + "[a-zA-Z0-9@:%._\\+~#?&//=]"
        + "{2,256}\\.[a-z]"
        + "{2,6}\\b([-a-zA-Z0-9@:%"
        + "._\\+~#?&//=]*)"
    )

    # Compile the ReGex
    compiled_regex = re.compile(regex)

    # If the string is empty
    # return false
    if candidate_url == None:
        return False

    # Return if the string
    # matched the ReGex
    if re.search(compiled_regex, candidate_url):
        return True
    else:
        return False


class Node:
    def __init__(self, dir_name="", rel_path=".", dir_sha=None):
        """
        Creating a Node object

        dir_name is the name of the directory the node contains information
        about rel_path is the actual path to the directory.

        The root node of a repository should be created by simply calling:

        root_node = Node()

        """
        self._dir = dir_name
        self._dir_sha = dir_sha
        self._type = "dir"
        self._dirs = []
        self._files = []
        self._files_sha = {}
        self._misc = []
        self._misc_sha = {}
        self._rel_path = rel_path + dir_name

    def __getFilePaths(self, current_path):
        """Returns the full paths to the files in the current folder."""
        rel_paths = []
        for fil in self._files:
            if current_path.endswith("/"):
                rel_paths.append(current_path + fil)
            else:
                rel_paths.append(current_path + "/" + fil)
        return rel_paths

    def __getMiscPaths(self, current_path):
        """Returns the full paths to the misc content in the current folder."""
        rel_paths = []
        for mis in self._misc:
            if current_path.endswith("/"):
                rel_paths.append(current_path + mis)
            else:
                rel_paths.append(current_path + "/" + mis)
        return rel_paths

    def __getDirPaths(self, current_path):
        rel_paths = []
        for node in self._dirs:
            if node.name[0] == "/":
                if current_path[-1] == "/":
                    rel_paths.append(current_path + node.name[1:])
                else:
                    rel_paths.append(current_path + node.name)
            elif current_path[-1] == "/":
                rel_paths.append(current_path + node.name)
            else:
                rel_paths.append(current_path + "/" + node.name)
        return rel_paths

    def __exists(self, current_path, path_to_obj):
        for fil in self.__getFilePaths(current_path):
            if fil == path_to_obj:
                return True
        for mis in self.__getMiscPaths(current_path):
            if mis == path_to_obj:
                return True
        for dir_path in self.__getDirPaths(current_path):
            if dir_path == path_to_obj:
                return True
        for node in self._dirs:
            if current_path.endswith("/"):
                if node.__exists(current_path + node.name, path_to_obj):
                    return True
            else:
                if node.__exists(current_path + "/" + node.name, path_to_obj):
                    return True
        return False

    def __type(self, path):
        for fil in self._files:
            if fil == path:
                return "file"
        for mis in self._misc:
            if mis == path:
                return "misc"
        for node in self._dirs:
            if path.count("/") == 0:
                if node.name == path:
                    return "dir"
            else:
                new_path = path.split("/")[1][0:]
                return node.__type(new_path)
        return None

    def __insert(self, current_path, content_path, content_type, content_sha):

        # Check if content_path contains folders
        sub_dir = None
        if content_path.startswith("./"):
            if content_path.count("/") > 1:
                # Ignore the first ./ so grab [1]
                sub_dir = content_path.split("/")[1]
                new_content_path = content_path.split(sub_dir)[1][1:]
        elif content_path.startswith("/"):
            if content_path.count("/") > 1:
                # Ignore the first / so grab [1]
                sub_dir = content_path.split("/")[1]
                new_content_path = content_path.split(sub_dir)[1][1:]
        elif content_path.count("/") > 0:
            sub_dir = content_path.split("/")[0]
            new_content_path = content_path.split(sub_dir)[1][0:]

        if sub_dir is not None:
            # Check if the directory has already been created
            found = False
            for node in self.nodes:
                if sub_dir == node.name:
                    found = True
                    node.__insert(
                        current_path + "/" + node.name,
                        new_content_path,
                        content_type,
                        content_sha,
                    )
            if not found:
                # Throw an error
                error_msg = "Cannot add content, missing sub folders.\n"
                error_msg += "content_path: " + content_path + "\n"
                raise Exception(error_msg)

        else:
            if content_type == "dir":
                if content_path.startswith("./"):
                    content_name = content_path[2:]
                elif content_path.startswith("/"):
                    content_name = content_path[1:]
                else:
                    content_name = content_path
                self._dirs.append(Node(content_name, self._rel_path + "/", content_sha))

            elif content_type == "file":
                self._files.append(content_path)
                self._files_sha[content_path] = content_sha
            else:
                self._misc.append(content_path)
                self._misc_sha[content_path] = content_sha

    def __sha(self, path):
        """
        Will return the sha of the file object or None if sha is not found.

        This is true with exception to the root directory which does not
        have a sha associated with it, and so it will also return None.
        """
        for fil in self._files:
            if fil == path:
                return self._files_sha[fil]
        for mis in self._misc:
            if mis == path:
                return self._misc_sha[fil]
        for node in self._dirs:
            if node.name == path:
                return self._dir_sha
            else:
                new_path = copy.deepcopy(path)
                new_path = "/".join(new_path.strip("/").new_path("/")[1:])
                return node.getSha(new_path)
        return None

    def insert(self, content_path, content_type, content_sha=None):
        """
        Record the contents of a directory by inserting it

        Will either store new information as a file, directory or misc type.
        If the content type is of type dir than a new node is created.
        """
        if not any(content_type in obj_name for obj_name in ["dir", "misc", "file"]):
            error_msg = "Unknown content type specified, allowed types are:\n"
            error_msg += "dir, misc, file\n"
            error_msg += "\ncontent_path: " + content_path
            error_msg += "\ncontent_type: " + content_type
            error_msg += "\ncontent_sha: " + content_sha
            raise Exception(error_msg)

        if any(content_path == obj_name for obj_name in ["", ".", "./"]):
            error_msg = "No content specified.\n"
            error_msg += "\ncontent_path: " + content_path
            error_msg += "\ncontent_type: " + content_type
            error_msg += "\ncontent_sha: " + content_sha
            raise Exception(error_msg)

        if content_sha is not None:
            if len(content_sha) != 40:
                error_msg = "sha must be contain 40 characters.\n"
                error_msg += "\ncontent_path: " + content_path
                error_msg += "\ncontent_type: " + content_type
                error_msg += "\ncontent_sha: " + content_sha
                raise Exception(error_msg)

        self.__insert("./", content_path, content_type, content_sha)

    @property
    def name(self):
        return self._dir

    @property
    def sha(self):
        return self._dir_sha

    @property
    def relative_path(self):
        return self._rel_path

    @property
    def files(self):
        """Returns non miscellaneous content and non folders"""
        return self._files

    @property
    def miscellaneous(self):
        """Returns miscellaneous content e.g. image files"""
        return self._misc

    @property
    def nodes(self):
        """
        Returns a list of all nodes in the current node.

        This will essentially be the directories.
        """
        return self._dirs

    def exists(self, path_to_obj):
        """
        Checks to see if a file object exists.

        Path should be the full path to the object. e.g.

        ./bin
        ./tests/test_unit.py
        ./image.png

        If the "./" are ommitted from the path it will be assumed that the
        file objects are in reference to the root path e.g. if

        bin
        tests/test_unit.py

        are passed in "./" will be prepended to the path.
        """
        # Check to see if path_to_obj is root node
        if path_to_obj == "." or path_to_obj == "./" or path_to_obj == "":
            return True

        if not path_to_obj.startswith("./"):
            if path_to_obj[0] == "/":
                path_to_obj = "." + path_to_obj
            else:
                path_to_obj = "./" + path_to_obj

        return self.__exists("./", path_to_obj)

    def getSha(self, path):
        """
        Will return the sha of the file object or None if sha is not found.

        This is true with exception to the root directory which does not
        have a sha associated with it, and so it will also return None.
        """
        if path.startswith("./"):
            if len(path) > 2:
                path = path[2:]
        if path.startswith("/"):
            if len(path) > 1:
                path = path[1:]

        for fil in self._files:
            if fil == path:
                return self._files_sha[fil]
        for mis in self._misc:
            if mis == path:
                return self._misc_sha[mis]
        for node in self._dirs:
            if node.name == path:
                return node._dir_sha
        for node in self._dirs:
            # Remove the dir1/ from dir1/dir2
            if path.startswith(node.name + "/"):
                new_path = path.split("/")[1][0:]
                found_sha = node.getSha(new_path)

                if found_sha is not None:
                    return found_sha
        return None

    def type(self, path):
        if path == "" or path == "." or path == "./":
            return "dir"
        return self.__type(path)

    @property
    def path(self):
        """Get the relative path of the current node."""
        return self._rel_path

    def __str__(self):
        """Get contents of node and all child nodes as a string."""
        return self._buildStr()

    def _buildStr(self, indent=""):
        """Contents in string format indenting with each folder."""
        content_string = ""
        for fil in self._files:
            content_string += indent + "file " + fil + "\n"
        for mis in self._misc:
            content_string += indent + "misc " + mis + "\n"
        for node in self._dirs:
            content_string += indent + "dir  " + node.name + "\n"
            content_string += node._buildStr(indent + "  ")
        return content_string

    def _findRelPaths(self, current_path, obj_name):
        """Contents in string format indenting with each folder."""
        rel_paths = []
        for fil in self.__getFilePaths(current_path):
            if fil.endswith(obj_name):
                rel_paths.append(fil)
        for mis in self.__getMiscPaths(current_path):
            if mis.endswith(obj_name):
                rel_paths.append(mis)
        for dir_path in self.__getDirPaths(current_path):
            if dir_path.endswith(obj_name):
                rel_paths.append(dir_path)

        for node in self._dirs:
            potential_paths = node._findRelPaths(
                current_path + "/" + node.name, obj_name
            )
            rel_paths += potential_paths
        return rel_paths

    @property
    def print(self):
        """Print contents of node and all child nodes."""
        print("Contents in folder: " + self._rel_path)
        for fil in self._files:
            print("file " + fil)
        for mis in self._misc:
            print("misc " + mis)
        for node in self._dirs:
            node.print

    def getRelativePaths(self, obj_name):
        """
        Get the path(s) to the object.

        In the case that an object exists in the directory tree but we don't
        know the path we can try to find it in the tree. E.g. if we are
        searching for 'common.py' and our directory structure actually has
        two instances:

        ./bin/common.py
        ./lib/file1.py
        ./common.py
        ./file2.py

        A list will be returned with the relative paths:

        ["./bin/common.py", "./common.py"]
        """
        return self._findRelPaths(".", obj_name)


class GitHubApp:

    """
    GitHubApp Class

    This class is responsible for authenticating against the app repository and
    interacting with the github api.
    """

    def __init__(
        self,
        app_id,
        name,
        user,
        repo_name,
        location_of_inheriting_class=None,
        verbosity=0,
    ):
        """
        The app is generic and provides a template, to create an app for a specefic repository the
        following arguments are needed:
        * the app id as provided when it is created on github
        * the name of the app
        * the owner of the repository it controls
        * the name of the repository it controls
        * the location of the github child class, should exist within a repo
        """
        self._app_id = app_id
        self._name = name
        self._user = user
        self._repo_name = repo_name
        self._verbosity = verbosity

        self._log = logging.getLogger(self._repo_name)
        self._log.setLevel(logging.INFO)

        fh = logging.FileHandler(self._repo_name + ".log", mode="w", encoding="utf-8")
        fh.setLevel(logging.INFO)
        self._log.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        self._log.addHandler(ch)

        self._config_file_dir = pathlib.Path(__file__).parent.absolute()
        self._config_file_name = "githubapp_" + str(self._app_id) + ".config"
        self._config_file_path = pathlib.Path.joinpath(
            self._config_file_dir, self._config_file_name
        )

        self._child_class_path = None
        if location_of_inheriting_class is not None:
            if os.path.isfile(location_of_inheriting_class):
                self._child_class_path = location_of_inheriting_class
        # Create an empty config file if one does not exist
        if not pathlib.Path.is_file(self._config_file_path):
            open(self._config_file_path, "a").close()

    @property
    def name(self):
        """Returns the name of the app."""
        return self._name

    def initialize(
        self,
        pem_file,
        use_wiki=False,
        ignore=False,
        create_branch=False,
        path_to_repo=None,
    ):
        """
        Sets basic properties of the app should be called before any other methods

        use_wiki - determines if by default commands will refer to the wiki repository
        create_branch - determines if you are giving the application the ability to create new
        branches
        pem_file - this is the authentication file needed to do anything with the github api.
        ignore - if this is set to true than images will not be uploaded to a seperate figures
        branch on the main repository. By default binary files are uploaded to a orphan branch so
        as to prevent bloatting the commit history.

        The initialization method is also responsible for authenticating with github and creating
        an access token. The access token is needed to do any further communication or run any other
        operations on github.
        """
        self._ignore = ignore
        self._use_wiki = use_wiki
        self._repo_url = (
            "https://api.github.com/repos/" + self._user + "/" + self._repo_name
        )
        if isinstance(create_branch, list):
            self._create_branch = create_branch[0]
        else:
            self._create_branch = create_branch
        self._default_branch = "develop"
        self._default_image_branch = "figures"
        self._branches = []
        self._branch_current_commit_sha = {}
        self._api_version = "application/vnd.github.v3+json"
        self._repo_root = Node()

        if path_to_repo is not None:
            # Check that the repo specified is valid
            if os.path.isdir(path_to_repo):
                # Check if we are overwriting an existing repo stored in the config file
                with open(self._config_file_path, "r") as file:
                    line = file.readline()
                    # Print a message if they are different
                    if line != path_to_repo:
                        self._log.info(
                            "Changing repo path from {} to {}".format(
                                line, path_to_repo
                            )
                        )

                with open(self._config_file_path, "w") as file:
                    file.write(path_to_repo)

                self._repo_path = path_to_repo
            else:
                error_msg = "The suggested repository path is not valid:\n{}".format(
                    path_to_repo
                )
                self._log.error(error_msg)
                raise
        else:
            if pathlib.Path.is_file(self._config_file_path):

                with open(self._config_file_path, "r") as file:
                    line = file.readline()
                    # Throw an error if the path is not valid
                    if not os.path.isdir(line):
                        error_msg = (
                            "The cached path to your repository is "
                            "not valid: ({})".format(line)
                        )
                        error_msg = (
                            error_msg
                            + "\nThe config file is located at: ({})".format(
                                self._config_file_path
                            )
                        )
                        error_msg = (
                            error_msg
                            + "\nConsider initializing the app "
                            + self._name
                            + " with the path of "
                        )
                        error_msg = error_msg + "repository it will be analyzing."
                        self._log.error(error_msg)
                    self._repo_path = line
            else:
                # If no config file exists throw an error
                error_msg = (
                    "No repository path is known to the " + self._name + ".\n"
                    "Please call --repository-path or -rp with the path the repository to register it.\n"
                )
                self._log.error(error_msg)
                raise

        self._app_wiki_dir = os.path.normpath(
            self._repo_path + "/../" + self._repo_name + ".wiki"
        )
        self._log.info(self._repo_name + " wiki dir is:")
        self._log.info(self._app_wiki_dir)

        if isinstance(pem_file, list):
            pem_file = pem_file[0]

        # Check that pem file is actually a file
        if not os.path.isfile(pem_file):
            error_msg = "Permissions file ({})".format(pem_file)
            error_msg = error_msg + " is not a valid file."
            raise Exception(error_msg)

        self._generateJWT(pem_file)
        self._generateInstallationId()
        self._generateAccessToken()

    def _generateJWT(self, pem_file):
        """
        Generates Json web token

        Method will take the permissions (.pem) file provided and populate the json web token
        attribute
        """
        # iss is the app id
        # Ensuring that we request an access token that expires after a minute
        payload = {
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(seconds=60),
            "iss": self._app_id,
        }

        PEM = None
        if pem_file == None:
            if "GITHUB_APP_PEM" in os.environ:
                pem_file = os.environ.get("GITHUB_APP_PEM")
            else:
                error_msg = "A pem file has not been specified and "
                error_msg += "GITHUB_APP_PEM env varaible is not defined"
                raise Exception(error_msg)

        self._log.info("File loc %s" % pem_file)
        certs = pem.parse_file(pem_file)
        PEM = str(certs[0])

        if PEM is None:
            error_msg = (
                "No permissions enabled for " + self._name + " app, "
                "either a pem file needs to be provided or the "
                "GITHUB_APP_PEM variable needs to be defined"
            )
            raise Exception(error_msg)

        self._jwt_token = jwt.encode(payload, PEM, algorithm="RS256")
        if isinstance(self._jwt_token, bytes):
            # Older versions of jwt return a byte string as opposed to a string
            self._jwt_token = self._jwt_token.decode("utf-8")

    def _PYCURL(self, header, url, option=None, custom_data=None):

        buffer_temp = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, url)
        c.setopt(pycurl.VERBOSE, self._verbosity)
        c.setopt(c.WRITEDATA, buffer_temp)
        c.setopt(c.HTTPHEADER, header)
        if option == "POST":
            c.setopt(c.POST, 1)
            c.setopt(c.POSTFIELDS, json.dumps(custom_data))
            c.setopt(c.POSTFIELDSIZE, len(json.dumps(custom_data)))
        elif option == "PUT":
            c.setopt(c.PUT, 1)
        elif option == "DELETE":
            c.setopt(c.CUSTOMREQUEST, "DELETE")
            c.setopt(c.POSTFIELDS, json.dumps(custom_data))
            c.setopt(c.POSTFIELDSIZE, len(json.dumps(custom_data)))

        if custom_data is not None:
            buffer_temp2 = BytesIO(json.dumps(custom_data).encode("utf-8"))
            c.setopt(c.READDATA, buffer_temp2)

        c.perform()
        code = c.getinfo(c.HTTP_CODE)
        c.close()

        if int(code) != 200:
            print("Code is {}".format(code))
            print(json.dumps(json.loads(buffer_temp.getvalue()), indent=4))

        return json.loads(buffer_temp.getvalue()), code

    def _generateInstallationId(self):
        """
        Generate an installation id

        This method will populate the installation id attribute using the
        internally stored json web token.
        """
        header = [
            "Authorization: Bearer " + str(self._jwt_token),
            "Accept: " + self._api_version,
        ]

        js_obj, _ = self._PYCURL(header, "https://api.github.com/app/installations")

        if isinstance(js_obj, list):
            js_obj = js_obj[0]

        # The installation id will be listed at the end of the url path
        self._install_id = js_obj["html_url"].rsplit("/", 1)[-1]

    def _generateAccessToken(self):
        """
        Creates an access token

        This method will populate the installation attribute using the
        installation id. The token is needed to authenticate any actions
        run by the application.
        """
        header = [
            "Authorization: Bearer " + str(self._jwt_token),
            "Accept: " + self._api_version,
        ]

        https_url_access_tokens = (
            "https://api.github.com/app/installations/"
            + self._install_id
            + "/access_tokens"
        )

        js_obj, _ = self._PYCURL(header, https_url_access_tokens, option="POST")

        if isinstance(js_obj, list):
            js_obj = js_obj[0]

        self._access_token = js_obj["token"]

        self._header = [
            "Authorization: token " + str(self._access_token),
            "Accept: " + self._api_version,
        ]

    def _fillTree(self, current_node, branch):
        """
        Creates a content tree of the branch

        This is an internal method that is meant to be used recursively
        to grab the contents of a branch of a remote repository.
        """
        nodes = current_node.nodes
        for node in nodes:

            js_obj, _ = self._PYCURL(
                self._header,
                self._repo_url + "/contents/" + node.path,
                custom_data={"branch": branch},
            )

            if isinstance(js_obj, list):
                for ob in js_obj:
                    node.insert(ob["name"], ob["type"], ob["sha"])
            else:
                node.insert(js_obj["name"], js_obj["type"], js_obj["sha"])

            self._fillTree(node, branch)

    def _getBranches(self):
        """Internal method for getting a list of the branches that are available on github."""
        page_found = True
        page_index = 1
        self._branches = []
        self._branch_current_commit_sha = {}
        while page_found:
            page_found = False
            js_obj_list, _ = self._PYCURL(
                self._header, self._repo_url + "/branches?page={}".format(page_index)
            )
            page_index = page_index + 1
            for js_obj in js_obj_list:
                page_found = True
                self._branches.append(js_obj["name"])
                self._branch_current_commit_sha.update(
                    {js_obj["name"]: js_obj["commit"]["sha"]}
                )

    def generateCandidateRepoPath(self):
        """Generate a possible path to the repo

        Provides a suggestion for the repository path the app is meant to work
        on. This will only provide a correct suggestion if the app code exists
        within the repository. If it is unable to identify a suitable suggestion
        it will return None.
        """
        if self._child_class_path is not None:
            index = self._child_class_path.rfind(self._repo_name)
            if index != -1:
                return self._child_class_path[0 : index + len(self._repo_name)]
        return None

    def getBranchMergingWith(self, branch):
        """Gets the name of the target branch of `branch` which it will merge with."""
        js_obj_list, _ = self._PYCURL(self._header, self._repo_url + "/pulls")
        self._log.info(
            "Checking if branch is open as a pr and what branch it is targeted to merge with.\n"
        )
        self._log.info("Checking branch %s\n" % (self._user + ":" + branch))
        for js_obj in js_obj_list:
            self._log.info("Found branch: %s.\n" % js_obj.get("head").get("label"))
            if js_obj.get("head").get("label") == self._user + ":" + branch:
                return js_obj.get("base").get("label").split(":", 1)[1]
        return None

    # Public Methods
    @property
    def branches(self):
        """
        Gets the branches of the repository

        This method will check to see if branches have already been collected from the github
        RESTful api. If the branch tree has not been collected it will update the branches
        attribute.
        """
        if not self._branches:
            self._getBranches()

        return self._branches

    def getLatestCommitSha(self, target_branch):
        """Does what it says gets the latest commit sha for the taget_branch."""
        if not self._branches:
            self._getBranches()
        return self._branch_current_commit_sha.get(target_branch)

    def branchExist(self, branch):
        """
        Determine if branch exists

        This method will determine if a branch exists on the github repository by pinging the
        github api.
        """
        return branch in self.branches

    def refreshBranchCache(self):
        """ "
        Method forces an update of the localy stored branch tree.

        Will update regardless of whether the class already contains a
        local copy. Might be necessary if the remote github repository
        is updated.
        """
        self._getBranches()

    def createBranch(self, branch, branch_to_fork_from=None):
        """
        Creates a git branch

        Will create a branch if it does not already exists, if the branch
        does exist will do nothing. The new branch will be created by
        forking it of the latest commit of the default branch
        """
        if branch_to_fork_from is None:
            branch_to_fork_from = self._default_branch
        if self.branchExist(branch):
            return

        if not self.branchExist(branch_to_fork_from):
            error_msg = (
                "Cannot create new branch: "
                + branch
                + " from "
                + branch_to_fork_from
                + " because "
                + branch_to_fork_from
                + " does not exist."
            )
            raise Exception(error_msg)

        self._PYCURL(
            self._header,
            self._repo_url + "/git/refs",
            option="POST",
            custom_data={
                "ref": "refs/heads/" + branch,
                "sha": self._branch_current_commit_sha[branch_to_fork_from],
            },
        )

    def _generateContent(self, head):
        contents = {}

        dir_path = head.relative_path
        for file_name in head.files:
            contents[dir_path + "/" + file_name] = [file_name, head.getSha(file_name)]
        for misc_name in head.miscellaneous:
            contents[dir_path + "/" + misc_name] = [misc_name, head.getSha(misc_name)]
        for node in head.nodes:
            node_content = self._generateContent(node)
            contents[dir_path + "/" + node.name] = [node.name, node.sha]
            contents.update(node_content)
        return contents

    def getContents(self, branch=None):
        """
        Returns the contents of a branch

        Returns the contents of a branch as a dictionary, where the key
        is the content path and the value is a list of the file folder name
        and the sha of the file/folder etc.
        """
        branch_tree = self.getBranchTree(branch)
        return self._generateContent(branch_tree)

    def remove(self, file_name_path, branch=None, file_sha=None, use_wiki=False):
        """
        This method will remove a file from the listed branch.

        Provide the file name and path with respect to the repository root.
        """
        if branch is None:
            branch = "master"
        # First check that the file exists in the repository
        branch_tree = self.getBranchTree(branch)
        # Only remove if the file actually exists
        if branch_tree.exists(file_name_path):

            if file_sha is None:
                # Attempt to get it from the branch tree
                file_sha = branch_tree.getSha(file_name_path)
                if file_sha is None:
                    error_msg = "Unable to remove existing file: "
                    error_msg += "{}, sha is unknown.".format(file_name_path)
                    raise Exception(error_msg)

            if file_name_path.startswith("/"):
                file_name_path = file_name_path[1:]
            elif file_name_path.startswith("./"):
                file_name_path = file_name_path[2:]

            message = self._name + " is removing {}".format(file_name_path)

            js_obj, _ = self._PYCURL(
                self._header,
                self._repo_url + "/contents/" + file_name_path,
                "DELETE",
                custom_data={
                    "branch": branch,
                    "sha": file_sha,
                    "message": message,
                },
            )

    def upload(self, file_name, branch=None, use_wiki=False):
        """
        This method attempts to upload a file to the specified branch.

        If the file is found to already exist it will be updated. Image
        files will by default be placed in a figures branch of the main
        repository, so as to not bloat the repositories commit history.
        """

        # Will only be needed if we are creating a branch
        branch_to_fork_from = self._default_branch

        if isinstance(file_name, list):
            file_name = file_name[0]
        if branch is None:
            branch = self._default_branch
        if file_name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif")
        ):
            self._log.info("Image file detected")
            if branch != self._default_image_branch and not self._ignore:
                self._log.warning(
                    "Note all images will be uploaded to a branch named: "
                    + self._default_image_branch
                    + " in the main repository."
                )
                self._log.warning("Unless the ignore flag is used.")
                branch = self._default_image_branch
                branch_to_fork_from = "master"
                self._use_wiki = False

        if self._use_wiki or use_wiki:
            if branch != "master":
                error_msg = (
                    "Files can only be uploaded to the wiki repositories master branch"
                )
                raise Exception(error_msg)

            if os.path.exists(
                self._app_wiki_dir + "/" + os.path.basename(os.path.normpath(file_name))
            ):
                commit_msg = "Updating file " + file_name
            else:
                commit_msg = "Adding file " + file_name
            repo = self.getWikiRepo(branch)
            destination = (
                self._app_wiki_dir + "/" + os.path.basename(os.path.normpath(file_name))
            )
            if not filecmp.cmp(file_name, destination):
                shutil.copy(file_name, destination)
            repo.index.add(
                [
                    str(
                        self._app_wiki_dir
                        + "/"
                        + os.path.basename(os.path.normpath(file_name))
                    )
                ]
            )
            repo.index.commit(commit_msg)
            repo.git.push("--set-upstream", "origin", repo.head.reference)
            return

        if self._create_branch:
            self.createBranch(branch, branch_to_fork_from)
        elif not self.branchExist(branch):
            error_msg = "branch: " + branch + " does not exist in repository."
            raise Exception(error_msg)

        contents = self.getContents(branch)

        file_found = False
        if os.path.basename(os.path.normpath(file_name)) in contents:
            self._log.warning(
                "File (%s) already exists in branch:%s"
                % (os.path.basename(os.path.normpath(file_name)), branch)
            )
            file_found = True

        # 2. convert file into base64 format
        # b is needed if it is a png or image file/ binary file
        with open(file_name, "rb") as f:
            data = f.read()
        encoded_file = base64.b64encode(data)

        # 3. upload the file, overwrite if exists already
        custom_data = {
            "message": "%s %s file %s"
            % (
                self._name,
                "overwriting" if file_found else "uploading",
                os.path.basename(os.path.normpath(file_name)),
            ),
            "name": self._name,
            "branch": branch,
            "content": encoded_file.decode("ascii"),
        }

        if file_found:
            custom_data["sha"] = contents[os.path.basename(os.path.normpath(file_name))]

        self._log.info(
            "Uploading file (%s) to branch (%s)"
            % (os.path.basename(os.path.normpath(file_name)), branch)
        )
        https_url_to_file = (
            self._repo_url
            + "/contents/"
            + os.path.basename(os.path.normpath(file_name))
        )

        self._PYCURL(self._header, https_url_to_file, "PUT", custom_data)

    def getBranchTree(self, branch=None):
        """
        Gets the contents of a branch as a tree

        Method will grab the contents of the specified branch from the
        remote repository. It will return the contents as a tree object.

        The tree object provides some basic functionality such as indicating
        the content type
        """
        # 1. Check if branch exists
        js_obj, _ = self._PYCURL(self._header, self._repo_url + "/branches", "GET")

        for obj in js_obj:
            if obj["name"] == branch:

                # Get the top level directory structure
                js_obj2, _ = self._PYCURL(
                    self._header,
                    self._repo_url + "/contents?ref=" + branch,
                    custom_data={"branch": branch},
                )

                for obj2 in js_obj2:
                    self._repo_root.insert(obj2["name"], obj2["type"], obj2["sha"])

                self._fillTree(self._repo_root, branch)

                return self._repo_root

        raise Exception("Branch missing from repository {}".format(branch))

    def cloneWikiRepo(self):
        """
        Clone a git repo

        Will clone the wiki repository if it does not exist, if it does
        exist it will update the access permissions by updating the wiki
        remote url. The repository is then returned.
        """
        wiki_remote = (
            "https://x-access-token:"
            + str(self._access_token)
            + "@github.com/"
            + self._user
            + "/"
            + self._repo_name
            + ".wiki.git"
        )
        if not os.path.isdir(str(self._app_wiki_dir)):
            repo = Repo.clone_from(wiki_remote, self._app_wiki_dir)
        else:
            repo = Repo(self._app_wiki_dir)
            g = git.cmd.Git(self._app_wiki_dir)
            self._log.info("Our remote url is %s" % wiki_remote)
            # git remote show origini
            self._log.info(g.execute(["git", "remote", "show", "origin"]))
            g.execute(["git", "remote", "set-url", "origin", wiki_remote])
            # Ensure local branches are synchronized with server
            g.execute(["git", "fetch"])
            # Will not overwrite files but will reset the index to match with the remote
            g.execute(["git", "reset", "--mixed", "origin/master"])

        return repo

    def getWikiRepo(self, branch):
        """
        Get the git wiki repo

        The github api has only limited supported for interacting with
        the github wiki, as such the best way to do this is to actually
        clone the github repository and interact with the git repo
        directly. This method will clone the repository if it does not
        exist. It will then return a repo object.
        """
        repo = self.cloneWikiRepo()
        return repo

    def postStatus(
        self, state, commit_sha=None, context=None, description=None, target_url=None
    ):
        if isinstance(state, list):
            state = state[0]

        """Post status of current commit."""
        self._log.info("Posting state: %s" % state)
        self._log.info("Posting context: %s" % context)
        self._log.info("Posting description: %s" % description)
        self._log.info("Posting url: %s" % target_url)
        state_list = ["pending", "failed", "error", "success"]

        if state not in state_list:
            raise Exception("Unrecognized state specified " + state)
        if commit_sha is None:
            commit_sha = os.getenv("CI_COMMIT_SHA")
        if commit_sha is None:
            commit_sha = os.getenv("TRAVIS_COMMIT")
        if commit_sha is None:
            error_msg = "CI_COMMIT_SHA and or TRAVIS_COMMIT not defined in "
            error_msg = error_msg + "environment cannot post status."
            raise Exception(error_msg)

        if len(commit_sha) != 40:
            error_msg = "Unconventional commit sha encountered (" + str(commit_sha)
            error_msg = error_msg + ") environment cannot post status. Sha "
            error_msg = error_msg + "should be 40 characters this one is "
            error_msg = error_msg + str(len(commit_sha))
            raise Exception(error_msg)

        custom_data_tmp = {"state": state}
        if context is not None:
            custom_data_tmp.update({"context": context})
        if description is not None:
            custom_data_tmp.update({"description": description})
        if target_url is not None:
            # Make sure has http(s) scheme
            if urlIsValid(target_url):
                custom_data_tmp.update({"target_url": target_url})
            else:
                error_msg = "Invalid url detected while posting attempting"
                error_msg = error_msg + " to post status.\n{}".format(target_url)
                raise Exception(error_msg)

        self._PYCURL(
            self._header,
            self._repo_url + "/statuses/" + commit_sha,
            option="POST",
            custom_data=custom_data_tmp
        )

    def getStatuses(self, commit_sha=None):
        """Get status of provided commit or commit has defined in the env vars."""
        if commit_sha is None:
            commit_sha = os.getenv("CI_COMMIT_SHA")
        if commit_sha is None:
            commit_sha = os.getenv("TRAVIS_COMMIT")
        if commit_sha is None:
            error_msg = (
                "Commit sha not provided and CI_COMMIT_SHA and "
                "TRAVIS_COMMIT not defined in environment cannot get status"
            )
            raise Exception(error_msg)

        # 1. Check if file exists if so get SHA
        js_obj, code = self._PYCURL(
            self._header, self._repo_url + "/commits/" + str(commit_sha) + "/statuses"
        )
        return js_obj, code, commit_sha

    def getState(self, commit_sha=None, index=0):
        """Get state of the provided commit at the provided index"""
        json_objs, code, commit_sha = self.getStatuses(commit_sha)

        if len(json_objs) <= index:
            error_msg = "Cannot get state of status at index {}".format(index)
            error_msg += "\nThere are only a total of statuses {}".format(
                len(json_objs)
            )
            error_msg += " at the provided commit ({})".format(commit_sha)
            raise Exception(error_msg)

        for count, json_obj in enumerate(json_objs):
            if count == index:
                return json_obj["state"], code, commit_sha

    def printStatus(self):
        js_obj = self.getStatuses()
        print(js_obj)
