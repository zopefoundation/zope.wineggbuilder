##############################################################################
#
# Copyright (c) 2008 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Main builder stuff
"""
import logging
import os
import sys
import tempfile
from collections import defaultdict

import ConfigParser
from distutils.version import StrictVersion

from zope.wineggbuilder import base

LOGGER = base.LOGGER


def getOption(config, section, name, default=None):
    try:
        return config.get(section, name)
    except ConfigParser.NoOptionError:
        return default


class Compiler(object):
    #hook to enable testing
    commandKlass = base.Command

    def __init__(self, name, config, options):
        self.name = name
        self.options = options
        self.read(config)

    def read(self, config):
        self.setup = getOption(config, self.name, 'setup')
        self.python = getOption(config, self.name, 'python')
        self.command = config.get(self.name, 'command')
        self.fileEnding = config.get(self.name, 'fileEnding')

    def checkBuild(self, package, version, files):
        """check whether build is required"""
        LOGGER.debug('Checking if build required for [%s] %s %s %s',
                     package.sectionName, package.name, version, self.name)
        needBuild = True
        fe = self.fileEnding.lower()
        for file in files:
            if file.lower().endswith(fe):
                needBuild = False
                break

        if needBuild:
            LOGGER.debug('Build required for [%s] %s %s %s',
                         package.sectionName, package.name, version, self.name)
        else:
            LOGGER.debug('Build not required for [%s] %s %s %s',
                         package.sectionName, package.name, version, self.name)
        return needBuild

    def build(self, package, version, files, sourceFolder, status):
        LOGGER.info('Starting build for [%s] %s %s %s',
                    package.sectionName, package.name, version, self.name)
        #we really need to build
        cmd = self.commandKlass(cwd=sourceFolder, exitOnError=False)
        command = self.command

        if self.options.dryrun:
            LOGGER.info("Dry run, no upload")
            command = command.replace('upload', '')
            status.setStatus(package, version, "dryrun", self)

        if self.setup:
            command = self.setup + '\r\n' + command

        idata = dict(version=version,
                     package=package,
                     sourceFolder=sourceFolder,
                     curdir=os.getcwd(),
                     python=self.python)
        command = command % idata

        LOGGER.debug('Running: %s\nIn: %s', command, sourceFolder)

        tmpfile = None
        if len(command.splitlines()) > 1:
            #in case there are more lines we got to do .bat file
            tmpfile = tempfile.mktemp(suffix='.bat')
            open(tmpfile, "w").write(command)
            command = tmpfile

        try:
            #this ought to build and upload the egg
            output = cmd.do(command)
            if 'failed' in output.lower():
                LOGGER.info("Something was wrong with the command. Output: %s",
                            output)
                status.setStatus(package, version, "failed", self)

            if 'running upload' in output \
                and 'Submitting' in output \
                and 'Server response (200): OK' in output:
                LOGGER.info("Upload seems to be OK.\n%s",
                            '\n'.join(output.splitlines()[-3:]))
                status.setStatus(package, version, "done", self)
        except KeyboardInterrupt:
            raise
        except base.CommandError:
            LOGGER.error("An error occurred while running the build "
                             "command, see output above")
            status.setStatus(package, version, "error", self)
        except:
            #prepare for the worst
            LOGGER.exception("An error occurred while running the build command")
            #continue without bailing out
            status.setStatus(package, version, "error", self)

        if tmpfile:
            os.remove(tmpfile)


class Package(object):
    #hook to enable testing
    pypiKlass = base.PYPI
    svnKlass = base.SVN
    gitKlass = base.Git
    dlKlass = base.Download

    def __init__(self, sectionName, config, options, compilers):
        self.sectionName = sectionName
        self.options = options
        self.read(sectionName, config, compilers)

    def read(self, sectionName, config, compilers):
        self.name = config.get(sectionName, 'package')
        self.pypiurl = getOption(config, sectionName, 'pypiurl',
            'https://pypi.python.org/simple/%s/' % self.name)
        self.repotype = getOption(config, sectionName, 'repotype', 'svn')
        if self.repotype == 'svn':
            self.tagurl = getOption(config, sectionName, 'tagurl',
                'svn://svn.zope.org/repos/main/%s/tags' % self.name)
            if self.tagurl.endswith('/'):
                self.tagurl = self.tagurl[:-1]
        if self.repotype == 'git':
            self.repourl = getOption(config, sectionName, 'repourl',
                'https://github.com/zopefoundation/%s.git' % self.name)
            if self.repourl.endswith('/'):
                self.repourl = self.repourl[:-1]
        if self.repotype == 'download':
            self.repourl = getOption(config, sectionName, 'repourl',
                'https://pypi.python.org/packages/source/%s/%s' % (self.name[0], self.name))
            if self.repourl.endswith('/'):
                self.repourl = self.repourl[:-1]
        if self.repotype == 'none':
            # the build/compile command will take care of it all (like lxml)
            pass
        self.minVersion = getOption(config, sectionName, 'minVersion')
        self.maxVersion = getOption(config, sectionName, 'maxVersion')
        self.needSource = bool(getOption(config, sectionName, 'needSource', 'True'))
        self.excludeVersions = getOption(
            config, sectionName, 'excludeVersions', '').split()
        self.targets = []
        for target in config.get(sectionName, 'targets').split():
            self.targets.append(compilers[target])

    def build(self, status):
        LOGGER.info("Processing %s [%s]", self.name, self.sectionName)

        #1 get versions from pypi
        pypi = self.pypiKlass()
        versions = pypi.package_releases(self.name, show_hidden=True)

        status.setVersions(self, versions)

        def skip(version):
            for target in self.targets:
                status.setStatus(self, version, "skip", target)

        #1.1 filter versions according to minVersion and maxVersion:
        if self.minVersion:
            minver = StrictVersion(self.minVersion)
            ov = []
            for v in versions:
                try:
                    if StrictVersion(v) >= minver:
                        ov.append(v)
                    else:
                        skip(v)
                except ValueError:
                    pass
            versions = ov

        if self.maxVersion:
            maxver = StrictVersion(self.maxVersion)
            ov = []
            for v in versions:
                try:
                    if StrictVersion(v) <= maxver:
                        ov.append(v)
                    else:
                        skip(v)
                except ValueError:
                    pass
            versions = ov

        ov = []
        for v in versions:
            if v in self.excludeVersions:
                skip(v)
            else:
                ov.append(v)
        versions = ov

        versions.sort()
        if len(versions) == 0:
            #nothing to do
            LOGGER.info('%s no versions, nothing to do', self.name)
            return

        #2 get file list of each version
        verFiles = defaultdict(list)
        gotSource = False

        for version in versions:
            for rdata in pypi.release_urls(self.name, version):
                filename = rdata['filename']
                LOGGER.debug('Got a file: %s', filename)
                verFiles[version].append(filename)

                if (filename.lower().endswith('.zip')
                    or filename.lower().endswith('.tar.gz')
                    or filename.lower().endswith('tgz')):
                    gotSource = True

        if self.needSource and not gotSource:
            LOGGER.info("No source release (.zip/.tar.gz/.tgz) found")

        for version in versions:
            #3 check whether we need a build
            needs = []
            for target in self.targets:
                needBuild = target.checkBuild(
                    self, version, verFiles.get(version, []))
                if needBuild:
                    needs.append(target)
                else:
                    status.setStatus(self, version, "existed", target)

            if needs:
                tmpfolder = tempfile.mkdtemp('wineggbuilder')
                try:
                    try:
                        if self.repotype == 'svn':
                            #3.1 svn co tag
                            svn = self.svnKlass(exitOnError=False)
                            svnurl = "%s/%s" % (self.tagurl, version)
                            svn.co(svnurl, tmpfolder)
                        if self.repotype == 'git':
                            git = self.gitKlass(exitOnError=False)
                            git.clone(self.repourl, tmpfolder)
                            git.checkout(version)
                        if self.repotype == 'download':
                            # download source from pypi
                            dl = self.dlKlass()
                            dl.download(self.name, self.repourl, tmpfolder, version)
                        if self.repotype == 'none':
                            # noop
                            pass
                    except OSError:
                        status.setStatus(self, version, "SVN/Git error")
                    else:
                        #3.2 build missing
                        for target in needs:
                            needBuild = target.build(
                                self, version, verFiles.get(version, []),
                                tmpfolder, status)
                finally:
                    #3.3 del temp folder
                    base.rmtree(tmpfolder)


class Status(object):
    def __init__(self, packages, targets):
        self.data = {}
        self.packages = packages
        self.targets = targets

        for p in packages:
            self.data[p.name] = {}

    def setVersions(self, package, versions):
        for v in versions:
            self.data[package.name].setdefault(v, {})
            for t in self.targets:
                self.data[package.name][v].setdefault(t, 'n/a')

    def setStatus(self, package, version, status, target=None):
        if target is None:
            # this is a version general status
            for t in self.targets:
                self.data[package.name][version][t] = status
        else:
            self.data[package.name][version][target.name] = status

    def log(self):
        text = ['\n']
        targets = sorted(self.targets.keys())
        vs = ' '.join(['=' * 10 for target in targets])
        sep = "%s %s" % ('=' * 20, vs)

        for pname in sorted(self.data.keys()):
            package = self.data[pname]
            vs = ' '.join([target.ljust(10) for target in targets])
            txt = "%s %s" % (pname.ljust(20), vs)
            text.append(sep)
            text.append(txt)
            text.append(sep)
            for vname in sorted(package.keys()):
                version = package[vname]
                if isinstance(version, basestring):
                    txt = "%20s %s" % (vname, version)
                else:
                    vs = ' '.join([version[target].ljust(10)
                                   for target in targets])
                    txt = "%20s %s" % (vname, vs)
                text.append(txt)
        output = '\n'.join(text)
        LOGGER.info(output)


class Builder(object):
    def __init__(self, configFileName, options):
        self.options = options
        LOGGER.info('loading configuration from %s', configFileName)

        config = ConfigParser.RawConfigParser()
        config.read(configFileName)

        self.compilers = {}
        for cmp in config.get(base.BUILD_SECTION, 'compilers').split():
            self.compilers[cmp] = Compiler(cmp, config, options)

        self.packages = []
        for section in sorted(config.sections()):
            if section == base.BUILD_SECTION:
                continue
            if section in self.compilers:
                continue

            self.packages.append(Package(section, config,
                                         options, self.compilers))

    def runCLI(self):
        LOGGER.info('Starting to build')

        status = Status(self.packages, self.compilers)

        for pkg in self.packages:
            try:
                pkg.build(status)
            except KeyboardInterrupt:
                raise
            except:
                #prepare for the worst
                LOGGER.exception("An error occurred while running the building %s",
                                 pkg.name)
                #continue without bailing out

        LOGGER.info('Done.')

        if self.options.status:
            status.log()


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
