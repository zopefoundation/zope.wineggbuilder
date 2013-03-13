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
    if len(command.splitlines()) > 1:
        #in case there are more lines we got to do .bat file
        tmpfile = tempfile.mktemp(suffix='.bat')
        open(tmpfile, "w").write(command)
        command = tmpfile

    base.Command(cwd=cwd).do(command)


class Build(object):
    def __init__(self, compiler):
        self.compiler = compiler

    def run(self):
        # let's stick to a non random temp folder
        bdir = addtmp('lxmlbuild')
        if os.path.exists(bdir):
            base.rmtree(bdir)
        os.makedirs(bdir)

        ###################
        url = 'http://sourceforge.net/projects/libpng/files/zlib/%s/zlib-%s.tar.bz2/download' % (
            ZLIB, ZLIB)
        zlib = 'zlib-%s.tar.bz2' % ZLIB
        zlibfolder = addtmp('zlib')
        download(url, zlib)
        extract(addtmp(zlib), bdir, 'zlib')

        cmd = r"nmake -f win32\Makefile.msc"
        command = self.compiler.setup + '\r\n' + cmd
        output = do(command, cwd=os.path.join(bdir, 'zlib'))

        ####################
        url = 'http://ftp.gnu.org/pub/gnu/libiconv/libiconv-%s.tar.gz' % ICONV
        iconv = 'iconv-%s.tar.bz2' % ICONV
        iconvfolder = addtmp('iconv')
        download(url, iconv)
        extract(addtmp(iconv), bdir, 'iconv')

        cmd = r"nmake /a -f Makefile.msvc NO_NLS=1"
        command = self.compiler.setup + '\r\n' + cmd
        output = do(command, cwd=os.path.join(bdir, 'iconv'))

        ####################
        url = 'ftp://xmlsoft.org/libxml2/libxml2-%s.tar.gz' % LIBXML
        libxml = 'libxml2-%s.tar.bz2' % LIBXML
        libxmlfolder = addtmp('libxml')
        download(url, libxml)
        extract(addtmp(libxml), bdir, 'libxml')

        cmd1 = r"cscript configure.js compiler=msvc iconv=yes zlib=yes include=%s;%s\include lib=%s;%s\lib" % (
            zlibfolder, iconvfolder, zlibfolder, iconvfolder)
        cmd2 = r"nmake all"
        command = self.compiler.setup + '\r\n' + cmd1 + '\r\n' + cmd2
        output = do(command, cwd=os.path.join(bdir, 'libxml', 'win32'))

        ####################
        url = 'ftp://xsltsoft.org/libxslt2/libxslt2-%s.tar.gz' % LIBXML
        libxslt = 'libxslt2-%s.tar.bz2' % LIBXSLT
        download(url, libxslt)
        extract(addtmp(libxslt), bdir, 'libxslt')

        cmd1 = r"cscript configure.js compiler=msvc iconv=yes zlib=yes include=%s\include;%s;%s\include lib=%s\win32\bin.msvc;%s;%s\lib" % (
            libxmlfolder, zlibfolder, iconvfolder, libxmlfolder, zlibfolder, iconvfolder)
        cmd2 = r"nmake all"
        command = self.compiler.setup + '\r\n' + cmd1 + '\r\n' + cmd2
        output = do(command, cwd=os.path.join(bdir, 'libxslt', 'win32'))


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
        print "Usage: %s [options] config1" % sys.argv[0]
        sys.exit(0)

    # we want the compilers from here
    builder = build.Builder(args[0], options)
    compilers = [builder.compilers[name] for name in TARGETS]

    for compiler in compilers:
        b = Build(compiler)
        b.run()

    # Remove the handler again.
    LOGGER.removeHandler(handler)

    # Exit cleanly.
    #sys.exit(0)
