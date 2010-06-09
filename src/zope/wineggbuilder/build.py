"""base classes

$Id$
"""
__docformat__ = 'ReStructuredText'
import StringIO
import base64
import httplib
import logging
import optparse
import os
import pkg_resources
import re
import subprocess
import sys
import tempfile
import urllib2
import urlparse
from collections import defaultdict

import BeautifulSoup
import ConfigParser

from zope.wineggbuilder import base

LOGGER = base.LOGGER

def getOption(config, section, name, default=None):
    try:
        return config.get(section, name)
    except ConfigParser.NoOptionError:
        self.uploadType = 'internal'


class Compiler(object):
    #hook to enable testing
    commandKlass = base.Command

    def __init__(self, name, config, options):
        self.name = name
        self.options = options
        self.read(config)

    def read(self, config):
        self.command = config.get(self.name, 'command')
        self.fileEnding = config.get(self.name, 'fileEnding')

    def checkBuild(self, package, version, files):
        """check whether build is required"""
        needBuild = True
        fe = self.fileEnding.lower()
        for file in files:
            if file.lower().endswith(fe):
                needBuild = False
                break
        return needBuild

    def build(self, package, version, files, sourceFolder):
        if self.checkBuild(package, version, files):
            #we really need to build
            #we have the source in sourceFolder
            cmd = self.commandKlass(cwd=sourceFolder, exitOnError=False)

            if len(self.command.splitlines()) > 1:
                #in case there are more lines we got to do .bat file
                tmpfile = tempfile.NamedTemporaryFile(suffix='.bat')
                command = tmpfile.name
                tmpfile.write(self.command)
                tmpfile.file.flush()
            else:
                command = self.command

            cmd.do(command)

            pass

class Package(object):
    #hook to enable testing
    pypiKlass = base.PYPI
    urlGetterKlass = base.URLGetter
    svnKlass = base.SVN

    def __init__(self, name, config, options, compilers):
        self.name = name
        self.options = options
        self.read(config, compilers)

    def read(self, config, compilers):
        self.pypiurl = config.get(self.name, 'pypiurl')
        self.tagurl = config.get(self.name, 'tagurl')
        if self.tagurl.endswith('/'):
            self.tagurl = self.tagurl[:-1]
        self.minVersion = getOption(config, self.name, 'minVersion')
        self.maxVersion = getOption(config, self.name, 'maxVersion')
        self.targets = []
        for target in config.get(self.name, 'targets').split():
            self.targets.append(compilers[target])

    def build(self):
        #1 get versions from pypi
        pypi = self.pypiKlass()
        versions = pypi.package_releases(self.name, show_hidden=True)

        #1.1 filter versions according to minVersion and maxVersion:


        #2 get file list of each version
        verFiles = defaultdict(list)
        simple = self.urlGetterKlass().get(self.pypiurl)
        soup = BeautifulSoup.BeautifulSoup(simple)
        VERSION = re.compile(self.name+r'-(\d+\.\d+(\.\d+){0,2})')
        for tag in soup('a'):
            cntnt = str(tag.contents[0]) # str: re does not like non-strings

            m = VERSION.search(cntnt)
            if m:
                version = m.group(1)
                if version not in versions:
                    continue
                verFiles[version].append(cntnt)

        svn = self.svnKlass()
        for version in versions:
            #3 check whether we need a build
            needBuild = False
            for target in self.targets:
                needBuild = target.checkBuild(
                    self, version, verFiles.get(version, []))
                if needBuild:
                    break

            if needBuild:
                tmpfolder = tempfile.mkdtemp('wineggbuilder')
                try:
                    #3.1 svn co tag
                    svnurl = "%s/%s" % (self.tagurl, version)
                    svn.co(svnurl, tmpfolder)

                    #3.2 build missing
                    for target in self.targets:
                        needBuild = target.build(
                            self, version, verFiles.get(version, []), tmpfolder)
                finally:
                    #3.3 del temp folder
                    base.rmtree(tmpfolder)



class Builder(object):
    def __init__(self, configFileName, options):
        config = ConfigParser.RawConfigParser()
        config.read(configFileName)

        self.compilers = {}
        for cmp in config.get(base.BUILD_SECTION, 'compilers').split():
            self.compilers[cmp] = Compiler(cmp, config, options)

        self.packages = []
        for pkg in config.get(base.BUILD_SECTION, 'packages').split():
            self.packages.append(Package(pkg, config, options, self.compilers))

    def runCLI(self):
        for pkg in self.packages:
            pkg.build()


def main(args=None):
    # Make sure we get the arguments.
    if args is None:
        args = sys.argv[1:]
    if not args:
        args = ['-h']

    # Set up logger handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(base.formatter)
    LOGGER.addHandler(handler)

    # Parse arguments
    options, args = base.parser.parse_args(args)

    LOGGER.setLevel(logging.INFO)
    if options.verbose:
        LOGGER.setLevel(logging.DEBUG)
    if options.quiet:
        LOGGER.setLevel(logging.FATAL)

    if len(args) == 0:
        print "No configuration was specified."
        print "Usage: %s [options] config1 config2 ..." % sys.argv[0]
        sys.exit(0)

    for configFileName in args:
        builder = Builder(configFileName, options)

        try:
            builder.runCLI()
        except KeyboardInterrupt:
            LOGGER.info("Quitting")
            sys.exit(0)

    # Remove the handler again.
    LOGGER.removeHandler(handler)

    # Exit cleanly.
    #sys.exit(0)
