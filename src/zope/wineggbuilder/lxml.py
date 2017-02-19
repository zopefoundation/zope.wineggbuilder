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
"""Building lxml... this is a complicated story

See http://lxml.de/build.html#static-linking-on-windows
"""
import logging
import os
import optparse
import requests
import sys
import shutil
import tarfile
import tempfile
import urllib2

from zope.wineggbuilder import base
from zope.wineggbuilder import build

LOGGER = base.LOGGER
LOGOUTPUT = False

PYPI_JSON_URL = "https://pypi.python.org/pypi/{}/json"

ZLIBVER = '1.2.7'
ZLIBURL = 'http://sourceforge.net/projects/libpng/files/zlib/%s/zlib-%s.tar.bz2/download' % (
          ZLIBVER, ZLIBVER)
ICONVVER = '1.9.1'
ICONVURL = 'http://ftp.gnu.org/pub/gnu/libiconv/libiconv-%s.tar.gz' % ICONVVER
LIBXMLVER = '2.9.3'
LIBXMLURL = 'ftp://xmlsoft.org/libxml2/libxml2-%s.tar.gz' % LIBXMLVER
LIBXSLTVER = '1.1.29'
LIBXSLTURL = 'ftp://xmlsoft.org/libxslt/libxslt-%s.tar.gz' % LIBXSLTVER
LXMLURL = 'https://pypi.python.org/packages/source/l/lxml/lxml-%s.tar.gz'


# we want to use a specific temp folder, not a random one
# that helps with debugging
TEMP = tempfile.gettempdir()

DOWNLOADS = None


def addtmp(name):
    return os.path.join(TEMP, name)


def download(url, fname):
    target = addtmp(fname)
    if DOWNLOADS:
        # we'll cache
        cached = os.path.join(DOWNLOADS, fname)
        if os.path.exists(cached):
            LOGGER.info("%s found in %s", fname, DOWNLOADS)
            shutil.copy(cached, target)
            return target

    if os.path.exists(target):
        LOGGER.info("%s already downloaded", fname)
        return target

    LOGGER.info("Downloading %s", url)
    remote = urllib2.urlopen(url)
    localFile = open(target, 'wb')
    localFile.write(remote.read())
    localFile.close()

    if DOWNLOADS:
        cached = os.path.join(DOWNLOADS, fname)
        shutil.copy(target, cached)

    LOGGER.info("Downloaded %s", fname)

    return target


def extract(fname, target, targetname):
    tf = tarfile.open(fname)
    tf.extractall(target)

    justfname = os.path.splitext(fname)[0]
    justfname = os.path.splitext(justfname)[0]
    justfname = os.path.basename(justfname)

    os.rename(os.path.join(target, justfname), os.path.join(target, targetname))

    LOGGER.info("Extracted %s to %s/%s", fname, target, targetname)


def do(command, cwd=None):
    tmpfile = None
    LOGGER.debug('%s in %s', command, cwd)
    if len(command.splitlines()) > 1:
        #in case there are more lines we got to do .bat file
        tmpfile = tempfile.mktemp(suffix='.bat')
        open(tmpfile, "w").write(command)
        command = tmpfile
        LOGGER.debug('running as %s', command)

    try:
        output = base.Command(cwd=cwd).do(command)
    finally:
        if tmpfile:
            os.remove(tmpfile)

    return output


def project_file(project, filename):
    # taken from https://github.com/dstufft/pypi-debian
    # Get the data from PyPI
    try:
        resp = requests.get(PYPI_JSON_URL.format(project))
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response.status_code == 404:
            raise ValueError("Could not find project '{}'".format(project))
    data = resp.json()

    # Determine if we're looking for a signature file and if we are correct
    # the filename to the non signature filename.
    if filename.endswith(".asc"):
        sig = True
        filename = filename[:-4]
    else:
        sig = False

    # Find out the URL on PyPI that points to this filename.
    for version, files in data["releases"].items():
        for file_ in files:
            if file_["filename"] == filename:
                # If we're looking for a signature, and this file has a
                # signature then we'll redirect to this URL.
                if sig and file_["has_sig"]:
                    return file_["url"] + ".asc"
                # If we're looking for a signature, and this file does not have
                # a signature then continue on looking for more files.
                elif sig:
                    continue
                # If we're not looking for a signature then redirect to this
                # URL.
                else:
                    return file_["url"]

    # If we've gotten to this point, then we were unable to find a filename
    # that matches the given filename for this project.
    raise ValueError(
        "Could not find filename '{}' for project '{}'".format(
            filename, project,
        )
    )


class CompileError(Exception):
    pass


class Build(object):
    def __init__(self, compiler):
        self.compiler = compiler

    def run(self, lxmlver):
        LOGGER.info("-----------------------")
        LOGGER.info("Building %s", self.compiler.name)
        # let's stick to a non random temp folder
        bdir = addtmp('lxmlbuild')
        if os.path.exists(bdir):
            base.rmtree(bdir)
        os.makedirs(bdir)

        idata = dict(version=lxmlver,
                     package='lxml',
                     #sourceFolder=sourceFolder,
                     curdir=os.getcwd(),
                     python=self.compiler.python)

        #####################
        zlib = 'zlib-%s.tar.bz2' % ZLIBVER
        zlibfolder = os.path.join(bdir, 'zlib')
        extract(download(ZLIBURL, zlib), bdir, 'zlib')

        cmd = r"nmake -f win32\Makefile.msc"
        command = self.compiler.setup + '\r\n' + cmd
        command = command % idata
        output = do(command, cwd=os.path.join(bdir, 'zlib'))
        if not LOGOUTPUT:
            output = 'suppressed'
        LOGGER.info('ZLIB build done, output: \n%s', output)

        ######################
        iconv = 'libiconv-%s.tar.bz2' % ICONVVER
        iconvfolder = os.path.join(bdir, 'libiconv')
        extract(download(ICONVURL, iconv), bdir, 'libiconv')

        cmd = r"nmake /a -f Makefile.msvc NO_NLS=1"
        command = self.compiler.setup + '\r\n' + cmd
        command = command % idata
        output = do(command, cwd=os.path.join(bdir, 'libiconv'))
        shutil.copy(
            os.path.join(iconvfolder, 'lib', 'iconv.lib'),
            os.path.join(iconvfolder, 'lib', 'iconv_a.lib'))
        if not LOGOUTPUT:
            output = 'suppressed'
        LOGGER.info('ICONV build done, output: \n%s', output)

        ######################
        libxml = 'libxml2-%s.tar.bz2' % LIBXMLVER
        libxmlfolder = os.path.join(bdir, 'libxml2')
        extract(download(LIBXMLURL, libxml), bdir, 'libxml2')

        cmd1 = r"cscript configure.js compiler=msvc iconv=yes zlib=yes include=%s;%s\include lib=%s;%s\lib" % (
            zlibfolder, iconvfolder, zlibfolder, iconvfolder)
        cmd2 = r"nmake all"
        command = self.compiler.setup + '\r\n' + cmd1 + '\r\n' + cmd2
        command = command % idata
        output = do(command, cwd=os.path.join(bdir, 'libxml2', 'win32'))
        if not LOGOUTPUT:
            output = 'suppressed'
        LOGGER.info('LIBXML build done, output: \n%s', output)

        ######################
        libxslt = 'libxslt-%s.tar.bz2' % LIBXSLTVER
        libxsltfolder = os.path.join(bdir, 'libxslt')
        extract(download(LIBXSLTURL, libxslt), bdir, 'libxslt')

        cmd1 = r"cscript configure.js compiler=msvc iconv=yes zlib=yes include=%s\include;%s;%s\include lib=%s\win32\bin.msvc;%s;%s\lib" % (
            libxmlfolder, zlibfolder, iconvfolder, libxmlfolder, zlibfolder, iconvfolder)
        cmd2 = r"nmake all"
        command = self.compiler.setup + '\r\n' + cmd1 + '\r\n' + cmd2
        command = command % idata
        output = do(command, cwd=os.path.join(bdir, 'libxslt', 'win32'))
        if not LOGOUTPUT:
            output = 'suppressed'
        LOGGER.info('LIBXSLT build done, output: \n%s', output)

        ####################
        lxml = 'lxml-%s.tar.gz' % lxmlver
        url = project_file('lxml', lxml)
        lxmlfolder = os.path.join(bdir, 'lxml')
        extract(download(url, lxml), bdir, 'lxml')

        # patch the include/lib folders for a static build
        subst = dict(zlib=zlibfolder, iconv=iconvfolder,
                     xml=libxmlfolder, xslt=libxsltfolder)

        newinc = r"""
STATIC_INCLUDE_DIRS = [
     r"%(xml)s\include",
     r"%(xslt)s",
     r"%(zlib)s",
     r"%(iconv)s\include"
     ]""" % subst

        newlib = r"""
STATIC_LIBRARY_DIRS = [
     r"%(xml)s\win32\bin.msvc",
     r"%(xslt)s\win32\bin.msvc",
     r"%(zlib)s",
     r"%(iconv)s\lib"
     ]
        """ % subst

        setuppy = open(os.path.join(lxmlfolder, 'setup.py'), 'rb').read()
        setuppy = setuppy.replace("STATIC_INCLUDE_DIRS = []", newinc)
        setuppy = setuppy.replace("STATIC_LIBRARY_DIRS = []", newlib)
        open(os.path.join(lxmlfolder, 'setup.py'), 'wb').write(setuppy)

        if not self.compiler.options.notest:
            # build the pyds
            cmd = "%s setup.py build --static" % self.compiler.python
            command = self.compiler.setup + '\r\n' + cmd
            command = command % idata
            output = do(command, cwd=lxmlfolder)

            # copy testing stuff to the build
            buildlibdir = None
            for fn in os.listdir(os.path.join(lxmlfolder, 'build')):
                if fn.startswith('lib.win'):
                    buildlibdir = os.path.join(lxmlfolder, 'build', fn)
                    break

            shutil.copy(
                os.path.join(lxmlfolder, 'selftest.py'),
                os.path.join(buildlibdir, 'selftest.py'))

            shutil.copy(
                os.path.join(lxmlfolder, 'selftest2.py'),
                os.path.join(buildlibdir, 'selftest2.py'))

            shutil.copytree(
                os.path.join(lxmlfolder, 'samples'),
                os.path.join(buildlibdir, 'samples'))

            command = "%s selftest.py" % self.compiler.python
            output = do(command, cwd=buildlibdir)
            LOGGER.info("selftest.py output: %s", output)
            output = output.lower()
            if 'failure' in output or 'error' in output:
                # an exitcode != 0 will bail out, but to be sure we'll check the output
                raise CompileError()

            command = "%s selftest2.py" % self.compiler.python
            output = do(command, cwd=buildlibdir)
            LOGGER.info("selftest2.py output: %s", output)
            output = output.lower()
            if 'failure' in output or 'error' in output:
                # an exitcode != 0 will bail out, but to be sure we'll check the output
                raise CompileError()

            # clean slate before making the binary
            base.rmtree(os.path.join(lxmlfolder, 'build'))

        # now let's build the binary
        if self.compiler.options.dryrun:
            cmd = "%s setup.py --static bdist_wininst" % self.compiler.python
        else:
            # upload to pypi if it's not a dry run
            cmd = "%s setup.py --static bdist_wininst upload" % self.compiler.python
        command = self.compiler.setup + '\r\n' + cmd
        command = command % idata
        output = do(command, cwd=lxmlfolder)

        # build.py Compiler.build needs this output
        LOGGER.info(output)

        # and leave stuff around for now
        #base.rmtree(bdir)


def getOptions(args):
    # Make sure we get the arguments.
    if args is None:
        args = sys.argv[1:]
    if not args:
        args = ['-h']

    # Parse arguments
    parser = optparse.OptionParser()
    parser.add_option(
        "-q", "--quiet", action="store_true",
        dest="quiet", default=False,
        help="When specified, no messages are displayed.")

    parser.add_option(
        "-v", "--verbose", action="store_true",
        dest="verbose", default=False,
        help="When specified, debug information is displayed.")

    parser.add_option(
        "-d", "--dryrun", action="store_true",
        dest="dryrun", default=False,
        help="When specified, no upload is done.")

    parser.add_option(
        "-n", "--notest", action="store_true",
        dest="notest", default=False,
        help="When specified, tests are ignored.")

    parser.add_option(
        "--downloads", action="store", type="string", dest="downloads",
        help="Specify a folder for download cache.")

    return parser.parse_args(args)


def main(args=None):
    options, args = getOptions(args)

    # Set up logger handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(base.formatter)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    if options.verbose:
        LOGGER.setLevel(logging.DEBUG)
    if options.quiet:
        LOGGER.setLevel(logging.FATAL)

    if len(args) == 0:
        print "No configuration was specified."
        print "Usage: %s [options] config-ini lxml-version lxml-target" % sys.argv[0]
        sys.exit(1)

    if options.downloads:
        global DOWNLOADS
        DOWNLOADS = options.downloads
    
    # we want the compilers specification from (args[0])
    builder = build.Builder(args[0], options)

    lxmlver = args[1]
    target = args[2]

    exitcode = 0
    compiler = builder.compilers[target]
    b = Build(compiler)
    try:
        b.run(lxmlver)
    except Exception:
        # meeh bare except, quite a lot of crap can happen
        LOGGER.exception("An error occurred while building")
        exitcode = 1

    # Remove the handler again.
    LOGGER.removeHandler(handler)

    # Exit cleanly.
    sys.exit(exitcode)
