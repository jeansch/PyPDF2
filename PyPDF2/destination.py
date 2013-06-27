# -*- coding: utf-8 -*-
#
# Copyright (c) 2006, Mathieu Fenniak
# Copyright (c) 2013, Jean Schurger <jean@schurger.org>
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import utils
from generic import NameObject, DictionaryObject


##
# A class representing a destination within a PDF file.
# See section 8.2.1 of the PDF 1.6 reference.
# Stability: Added in v1.10, will exist for all v1.x releases.
class Destination(DictionaryObject):
    def __init__(self, title, page, typ, *args):
        DictionaryObject.__init__(self)
        self[NameObject("/Title")] = title
        self[NameObject("/Page")] = page
        self[NameObject("/Type")] = typ

        # from table 8.2 of the PDF 1.6 reference.
        if typ == "/XYZ":
            (self[NameObject("/Left")], self[NameObject("/Top")],
                self[NameObject("/Zoom")]) = args
        elif typ == "/FitR":
            (self[NameObject("/Left")], self[NameObject("/Bottom")],
                self[NameObject("/Right")], self[NameObject("/Top")]) = args
        elif typ in ["/FitH", "FitBH"]:
            self[NameObject("/Top")], = args
        elif typ in ["/FitV", "FitBV"]:
            self[NameObject("/Left")], = args
        elif typ in ["/Fit", "FitB"]:
            pass
        else:
            raise utils.PdfReadError("Unknown Destination Type: %r" % typ)

    ##
    # Read-only property accessing the destination title.
    # @return A string.
    title = property(lambda self: self.get("/Title"))

    ##
    # Read-only property accessing the destination page.
    # @return An integer.
    page = property(lambda self: self.get("/Page"))

    ##
    # Read-only property accessing the destination type.
    # @return A string.
    typ = property(lambda self: self.get("/Type"))

    ##
    # Read-only property accessing the zoom factor.
    # @return A number, or None if not available.
    zoom = property(lambda self: self.get("/Zoom", None))

    ##
    # Read-only property accessing the left horizontal coordinate.
    # @return A number, or None if not available.
    left = property(lambda self: self.get("/Left", None))

    ##
    # Read-only property accessing the right horizontal coordinate.
    # @return A number, or None if not available.
    right = property(lambda self: self.get("/Right", None))

    ##
    # Read-only property accessing the top vertical coordinate.
    # @return A number, or None if not available.
    top = property(lambda self: self.get("/Top", None))

    ##
    # Read-only property accessing the bottom vertical coordinate.
    # @return A number, or None if not available.
    bottom = property(lambda self: self.get("/Bottom", None))
