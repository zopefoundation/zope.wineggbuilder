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
"""
__docformat__ = 'ReStructuredText'
import logging
import os
import optparse
import re
import sys
import shutil
import tarfile
import tempfile
import urllib2
from collections import defaultdict

import BeautifulSoup
import ConfigParser
from distutils.version import StrictVersion

from zope.wineggbuilder import base
from zope.wineggbuilder import build

LOGGER = base.LOGGER
TARGETS = """
    py26_32 py26_64
    py27_32 py27_64
    py32_32 py32_64""".split()
TARGETS = """
    py26_32 py26_64""".split()

ZLIB = '1.2.7'
ICONV = '1.9.1'
LIBXML = '2.9.0'
LIBXSLT = '1.1.28'

TEMP = tempfile.gettempdir()

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


def addtmp(name):
    return os.path.join(TEMP, name)


def download(url, fname):
    target = addtmp(fname)
    # we'll cache in temp
    if os.path.exists(target):
        LOGGER.info("%s already downloaded", fname)
        return True

    LOGGER.info("Downloading %s", url)
    remote = urllib2.urlopen(url)
    localFile = open(target, 'wb')
    localFile.write(remote.read())
    localFile.close()

    LOGGER.info("Downloaded %s", fname)

    return True


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
    if len(command.splitlines()) > 1:
        #in case there are more lines we got to do .bat file
        tmpfile = tempfile.mktemp(suffix='.bat')
        open(tmpfile, "w").write(command)
        command = tmpfile

    LOGGER.debug('%s in %s', command, cwd)
    try:
        output = base.Command(cwd=cwd).do(command)
    finally:
        if tmpfile:
            os.remove(tmpfile)

    return output


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

        #####################
        url = 'http://sourceforge.net/projects/libpng/files/zlib/%s/zlib-%s.tar.bz2/download' % (
            ZLIB, ZLIB)
        zlib = 'zlib-%s.tar.bz2' % ZLIB
        zlibfolder = os.path.join(bdir, 'zlib')
        download(url, zlib)
        extract(addtmp(zlib), bdir, 'zlib')

        cmd = r"nmake -f win32\Makefile.msc"
        command = self.compiler.setup + '\r\n' + cmd
        output = do(command, cwd=os.path.join(bdir, 'zlib'))

        ######################
        url = 'http://ftp.gnu.org/pub/gnu/libiconv/libiconv-%s.tar.gz' % ICONV
        iconv = 'libiconv-%s.tar.bz2' % ICONV
        iconvfolder = os.path.join(bdir, 'libiconv')
        download(url, iconv)
        extract(addtmp(iconv), bdir, 'libiconv')

        cmd = r"nmake /a -f Makefile.msvc NO_NLS=1"
        command = self.compiler.setup + '\r\n' + cmd
        output = do(command, cwd=os.path.join(bdir, 'libiconv'))
        shutil.copy(
            os.path.join(iconvfolder, 'lib', 'iconv.lib'),
            os.path.join(iconvfolder, 'lib', 'iconv_a.lib'))

        ######################
        url = 'ftp://xmlsoft.org/libxml2/libxml2-%s.tar.gz' % LIBXML
        libxml = 'libxml2-%s.tar.bz2' % LIBXML
        libxmlfolder = os.path.join(bdir, 'libxml2')
        download(url, libxml)
        extract(addtmp(libxml), bdir, 'libxml2')

        cmd1 = r"cscript configure.js compiler=msvc iconv=yes zlib=yes include=%s;%s\include lib=%s;%s\lib" % (
            zlibfolder, iconvfolder, zlibfolder, iconvfolder)
        cmd2 = r"nmake all"
        command = self.compiler.setup + '\r\n' + cmd1 + '\r\n' + cmd2
        output = do(command, cwd=os.path.join(bdir, 'libxml2', 'win32'))

        ######################
        url = 'ftp://xmlsoft.org/libxslt/libxslt-%s.tar.gz' % LIBXSLT
        libxslt = 'libxslt-%s.tar.bz2' % LIBXSLT
        libxsltfolder = os.path.join(bdir, 'libxslt')
        download(url, libxslt)
        extract(addtmp(libxslt), bdir, 'libxslt')

        cmd1 = r"cscript configure.js compiler=msvc iconv=yes zlib=yes include=%s\include;%s;%s\include lib=%s\win32\bin.msvc;%s;%s\lib" % (
            libxmlfolder, zlibfolder, iconvfolder, libxmlfolder, zlibfolder, iconvfolder)
        cmd2 = r"nmake all"
        command = self.compiler.setup + '\r\n' + cmd1 + '\r\n' + cmd2
        output = do(command, cwd=os.path.join(bdir, 'libxslt', 'win32'))

        ####################
        url = 'https://pypi.python.org/packages/source/l/lxml/lxml-%s.tar.gz' % lxmlver
        lxml = 'lxml-%s.tar.gz' % lxmlver
        lxmlfolder = os.path.join(bdir, 'lxml')
        download(url, lxml)
        extract(addtmp(lxml), bdir, 'lxml')

        subst = dict(zlib=zlibfolder, iconv=iconvfolder,
                   xml=libxmlfolder, xslt=libxsltfolder)
        newinc = r"""
STATIC_INCLUDE_DIRS = [
     r"%(xml)s\include",
     r"%(xslt)s",
     r"%(zlib)s",
     r"%(iconv)s\include"
     ]"""% subst

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

        cmd = "%s setup.py build --static" % self.compiler.python
        command = self.compiler.setup + '\r\n' + cmd
        output = do(command, cwd=lxmlfolder)

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
        command = "%s selftest2.py" % self.compiler.python
        output = do(command, cwd=buildlibdir)
        LOGGER.info("selftest2.py output: %s", output)

        if self.compiler.options.dryrun:
            cmd = "%s setup.py --static bdist_wininst" % self.compiler.python
        else:
            cmd = "%s setup.py --static bdist_wininst upload" % self.compiler.python
        command = self.compiler.setup + '\r\n' + cmd
        output = do(command, cwd=lxmlfolder)


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
    options, args = parser.parse_args(args)

    LOGGER.setLevel(logging.INFO)
    if options.verbose:
        LOGGER.setLevel(logging.DEBUG)
    if options.quiet:
        LOGGER.setLevel(logging.FATAL)

    if len(args) == 0:
        print "No configuration was specified."
        print "Usage: %s [options] lxml-version config1" % sys.argv[0]
        sys.exit(0)

    # we want the compilers from here
    lxmlver = args[0]
    builder = build.Builder(args[1], options)
    compilers = [builder.compilers[name] for name in TARGETS]

    for compiler in compilers:
        b = Build(compiler)
        b.run(lxmlver)

    # Remove the handler again.
    LOGGER.removeHandler(handler)

    # Exit cleanly.
    #sys.exit(0)
