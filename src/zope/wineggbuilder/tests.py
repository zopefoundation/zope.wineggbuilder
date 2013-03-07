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
"""tests
"""
__docformat__ = 'ReStructuredText'

import unittest
from zope.testing import doctest
import pprint


def doctest_versions():
    """Check some assumptions on version comparison

    >>> from distutils.version import StrictVersion
    >>> v4 = StrictVersion('4.0.0')
    >>> v4a = StrictVersion('4.0.0a1')

    >>> v4 > v4a
    True

    >>> v4 == v4a
    False

    >>> v4 < v4a
    False
    """


def test_suite():
    return unittest.TestSuite((
        doctest.DocFileSuite('test.txt',
            optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
            globs={'pprint': pprint}
            ),
        doctest.DocTestSuite(
            optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS,
        )
        ))


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
