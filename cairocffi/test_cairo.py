"""
    cairocffi.tests
    ~~~~~~~~~~~~~~~

    Test suite for cairocffi.

    :copyright: Copyright 2013-2019 by Simon Sapin
    :license: BSD, see LICENSE for details.

"""

import array
import base64
import contextlib
import gc
import io
import math
import os
import shutil
import sys
import tempfile

import cairocffi
import pikepdf
import pytest

from . import (
    PDF_METADATA_AUTHOR, PDF_METADATA_CREATE_DATE, PDF_METADATA_CREATOR,
    PDF_METADATA_KEYWORDS, PDF_METADATA_MOD_DATE, PDF_METADATA_SUBJECT,
    PDF_METADATA_TITLE, PDF_OUTLINE_FLAG_BOLD, PDF_OUTLINE_FLAG_OPEN,
    PDF_OUTLINE_ROOT, SVG_UNIT_PC, SVG_UNIT_PT, SVG_UNIT_PX, SVG_UNIT_USER,
    TAG_LINK, Context, FontFace, FontOptions, ImageSurface, LinearGradient,
    Matrix, Pattern, PDFSurface, PSSurface, RadialGradient, RecordingSurface,
    ScaledFont, SolidPattern, Surface, SurfacePattern, SVGSurface, ToyFontFace,
    cairo_version, cairo_version_string)

if sys.byteorder == 'little':
    def pixel(argb):  # pragma: no cover
        """Convert a 4-byte ARGB string to native-endian."""
        return argb[::-1]
else:
    def pixel(argb):  # pragma: no cover
        """Convert a 4-byte ARGB string to native-endian."""
        return argb


@contextlib.contextmanager
def temp_directory():
    tempdir = tempfile.mkdtemp('é')
    assert 'é' in tempdir  # Test non-ASCII filenames
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)


def round_tuple(values):
    return tuple(round(v, 6) for v in values)


def assert_raise_finished(func, *args, **kwargs):
    with pytest.raises(cairocffi.CairoError) as exc:
        func(*args, **kwargs)
    assert 'SURFACE_FINISHED' in str(exc) or 'ExceptionInfo' in str(exc)


def test_cairo_version():
    major, minor, micro = map(int, cairo_version_string().split('.'))
    assert cairo_version() == major * 10000 + minor * 100 + micro


def test_install_as_pycairo():
    cairocffi.install_as_pycairo()
    import cairo
    assert cairo is cairocffi


def test_image_surface():
    assert ImageSurface.format_stride_for_width(
        cairocffi.FORMAT_ARGB32, 100) == 400
    assert ImageSurface.format_stride_for_width(
        cairocffi.FORMAT_A8, 100) == 100

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 20, 30)
    assert surface.get_format() == cairocffi.FORMAT_ARGB32
    assert surface.get_width() == 20
    assert surface.get_height() == 30
    assert surface.get_stride() == 20 * 4

    with pytest.raises(ValueError):
        # buffer too small
        data = array.array('B', b'\x00' * 799)
        ImageSurface.create_for_data(data, cairocffi.FORMAT_ARGB32, 10, 20)
    data = array.array('B', b'\x00' * 800)
    surface = ImageSurface.create_for_data(data, cairocffi.FORMAT_ARGB32,
                                           10, 20, stride=40)
    context = Context(surface)
    # The default source is opaque black:
    assert context.get_source().get_rgba() == (0, 0, 0, 1)
    context.paint_with_alpha(0.5)
    assert data.tobytes() == pixel(b'\x80\x00\x00\x00') * 200


def test_image_bytearray_buffer():
    if '__pypy__' in sys.modules:
        pytest.xfail()
    # Also test buffers through ctypes.c_char.from_buffer,
    # not available on PyPy
    data = bytearray(800)
    surface = ImageSurface.create_for_data(data, cairocffi.FORMAT_ARGB32,
                                           10, 20, stride=40)
    Context(surface).paint_with_alpha(0.5)
    assert data == pixel(b'\x80\x00\x00\x00') * 200


@pytest.mark.xfail(cairo_version() < 11200,
                   reason='Cairo version too low')
def test_surface_create_similar_image():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 20, 30)
    similar = surface.create_similar_image(cairocffi.FORMAT_A8, 4, 100)
    assert isinstance(similar, ImageSurface)
    assert similar.get_content() == cairocffi.CONTENT_ALPHA
    assert similar.get_format() == cairocffi.FORMAT_A8
    assert similar.get_width() == 4
    assert similar.get_height() == 100


@pytest.mark.xfail(cairo_version() < 11000,
                   reason='Cairo version too low')
def test_surface_create_for_rectangle():
    surface = ImageSurface(cairocffi.FORMAT_A8, 4, 4)
    data = surface.get_data()
    assert data[:] == b'\x00' * 16
    Context(surface.create_for_rectangle(1, 1, 2, 2)).paint()
    assert data[:] == (
        b'\x00\x00\x00\x00'
        b'\x00\xFF\xFF\x00'
        b'\x00\xFF\xFF\x00'
        b'\x00\x00\x00\x00')


def test_surface():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 20, 30)
    similar = surface.create_similar(cairocffi.CONTENT_ALPHA, 4, 100)
    assert isinstance(similar, ImageSurface)
    assert similar.get_content() == cairocffi.CONTENT_ALPHA
    assert similar.get_format() == cairocffi.FORMAT_A8
    assert similar.get_width() == 4
    assert similar.get_height() == 100
    assert similar.has_show_text_glyphs() is False
    assert PDFSurface(None, 1, 1).has_show_text_glyphs() is True
    surface.copy_page()
    surface.show_page()
    surface.mark_dirty()
    surface.mark_dirty_rectangle(1, 2, 300, 12000)
    surface.flush()

    surface.set_device_offset(14, 3)
    assert surface.get_device_offset() == (14, 3)

    surface.set_fallback_resolution(15, 6)
    assert surface.get_fallback_resolution() == (15, 6)

    context = Context(surface)
    assert isinstance(context.get_target(), ImageSurface)
    surface_map = cairocffi.surfaces.SURFACE_TYPE_TO_CLASS
    try:
        del surface_map[cairocffi.SURFACE_TYPE_IMAGE]
        target = context.get_target()
        assert target._pointer == surface._pointer
        assert isinstance(target, Surface)
        assert not isinstance(target, ImageSurface)
    finally:
        surface_map[cairocffi.SURFACE_TYPE_IMAGE] = ImageSurface

    surface.finish()
    assert_raise_finished(surface.copy_page)
    assert_raise_finished(surface.show_page)
    assert_raise_finished(surface.set_device_offset, 1, 2)
    assert_raise_finished(surface.set_fallback_resolution, 3, 4)


def test_target_lifetime():
    # Test our work around for
    # Related CFFI bug: https://bitbucket.org/cffi/cffi/issue/92/
    if not hasattr(sys, 'getrefcount'):
        pytest.xfail()  # PyPy
    gc.collect()  # Clean up stuff from other tests
    target = io.BytesIO()
    initial_refcount = sys.getrefcount(target)
    assert len(cairocffi.surfaces.KeepAlive.instances) == 0
    surface = PDFSurface(target, 100, 100)
    # The target is in a KeepAlive object
    assert len(cairocffi.surfaces.KeepAlive.instances) == 1
    assert sys.getrefcount(target) == initial_refcount + 1
    del surface
    gc.collect()  # Make sure surface is collected
    assert len(cairocffi.surfaces.KeepAlive.instances) == 0
    assert sys.getrefcount(target) == initial_refcount


@pytest.mark.xfail(cairo_version() < 11000,
                   reason='Cairo version too low')
def test_mime_data():
    surface = PDFSurface(None, 1, 1)
    assert surface.get_mime_data('image/jpeg') is None
    gc.collect()  # Clean up KeepAlive stuff from other tests
    assert len(cairocffi.surfaces.KeepAlive.instances) == 0
    surface.set_mime_data('image/jpeg', b'lol')
    assert len(cairocffi.surfaces.KeepAlive.instances) == 1
    assert surface.get_mime_data('image/jpeg')[:] == b'lol'

    surface.set_mime_data('image/jpeg', None)
    assert len(cairocffi.surfaces.KeepAlive.instances) == 0
    if cairo_version() >= 11200:
        # This actually segfauts on cairo 1.10.x
        assert surface.get_mime_data('image/jpeg') is None
    surface.finish()
    assert_raise_finished(surface.set_mime_data, 'image/jpeg', None)


@pytest.mark.xfail(cairo_version() < 11200,
                   reason='Cairo version too low')
def test_supports_mime_type():
    # Also test we get actual booleans:
    assert PDFSurface(None, 1, 1).supports_mime_type('image/jpeg') is True
    surface = ImageSurface(cairocffi.FORMAT_A8, 1, 1)
    assert surface.supports_mime_type('image/jpeg') is False


@pytest.mark.xfail(cairo_version() < 11400,
                   reason='Cairo version too low')
def test_device_scale():
    surface = PDFSurface(None, 1, 1)
    assert surface.get_device_scale() == (1, 1)
    surface.set_device_scale(2, 3)
    assert surface.get_device_scale() == (2, 3)


@pytest.mark.xfail(cairo_version() < 11504,
                   reason='Cairo version too low')
def test_metadata():
    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    surface.set_metadata(PDF_METADATA_TITLE, 'title')
    surface.set_metadata(PDF_METADATA_SUBJECT, 'subject')
    surface.set_metadata(PDF_METADATA_CREATOR, 'creator')
    surface.set_metadata(PDF_METADATA_AUTHOR, 'author')
    surface.set_metadata(PDF_METADATA_KEYWORDS, 'keywords')
    surface.set_metadata(PDF_METADATA_CREATE_DATE, '2013-07-21T23:46:00+01:00')
    surface.set_metadata(PDF_METADATA_MOD_DATE, '2013-07-21T23:46:00Z')
    surface.finish()
    pdf = pikepdf.Pdf.open(file_obj)
    assert pdf.docinfo['/Title'] == "title"
    assert pdf.docinfo['/Subject'] == "subject"
    assert pdf.docinfo['/Creator'] == "creator"
    assert pdf.docinfo['/Author'] == "author"
    assert pdf.docinfo['/Keywords'] == "keywords"
    # cairo 1.17.4 adds an apostrophe at the end of dates:
    # https://gitlab.freedesktop.org/cairo/cairo/-/issues/392
    assert str(pdf.docinfo['/CreationDate']).startswith("20130721234600+01'00")
    assert pdf.docinfo['/ModDate'] == "20130721234600Z"


@pytest.mark.xfail(cairo_version() < 11504,
                   reason='Cairo version too low')
def test_outline():
    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    outline = surface.add_outline(
        PDF_OUTLINE_ROOT, 'title 1', 'page=1 pos=[1 1]',
        PDF_OUTLINE_FLAG_OPEN & PDF_OUTLINE_FLAG_BOLD)
    surface.add_outline(outline, 'title 2', 'page=1 pos=[1 1]')
    surface.finish()
    pdf = pikepdf.Pdf.open(file_obj)
    outline = pdf.open_outline()
    assert outline.root[0].title == "title 1"
    assert outline.root[0].children[0].title == "title 2"


@pytest.mark.xfail(cairo_version() < 11504,
                   reason='Cairo version too low')
def test_page_label():
    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    surface.set_page_label('abc')
    surface.finish()
    pdf = pikepdf.Pdf.open(file_obj)
    assert pdf.pages[0].label == "abc"


@pytest.mark.xfail(cairo_version() < 11504,
                   reason='Cairo version too low')
def test_tag():
    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 10, 10)
    context = Context(surface)
    context.tag_begin('Document')
    context.tag_begin(
        TAG_LINK,
        attributes='rect=[1 2 4 5] uri=\'https://cairocffi.readthedocs.io/\'')
    context.set_source_rgba(1, 0, .5, 1)
    context.rectangle(2, 3, 4, 5)
    context.fill()
    context.tag_end(TAG_LINK)
    context.tag_end('Document')
    context.show_page()
    surface.finish()
    pdf = pikepdf.Pdf.open(file_obj)
    assert '"/URI": "https://cairocffi.readthedocs.io/"' in str(pdf.objects)
    assert '"/S": "/Document"' in str(pdf.objects)


@pytest.mark.xfail(cairo_version() < 11504,
                   reason='Cairo version too low')
def test_thumbnail_size():
    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    surface.set_thumbnail_size(1, 1)
    surface.finish()
    pdf_bytes1 = file_obj.getvalue()

    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    surface.set_thumbnail_size(9, 9)
    surface.finish()
    pdf_bytes2 = file_obj.getvalue()

    assert len(pdf_bytes1) < len(pdf_bytes2)


@pytest.mark.xfail(cairo_version() < 11510,
                   reason='Cairo version too low')
def test_document_unit():
    surface = SVGSurface(None, 1, 2)
    assert surface.get_document_unit() in (SVG_UNIT_USER, SVG_UNIT_PT)

    file_obj = io.BytesIO()
    surface = SVGSurface(file_obj, 1, 2)
    surface.set_document_unit(SVG_UNIT_PX)
    assert surface.get_document_unit() == SVG_UNIT_PX
    surface.finish()
    pdf_bytes = file_obj.getvalue()
    assert b'width="1px"' in pdf_bytes
    assert b'height="2px"' in pdf_bytes

    file_obj = io.BytesIO()
    surface = SVGSurface(file_obj, 1, 2)
    surface.set_document_unit(SVG_UNIT_PC)
    assert surface.get_document_unit() == SVG_UNIT_PC
    surface.finish()
    pdf_bytes = file_obj.getvalue()
    assert b'width="1pc"' in pdf_bytes
    assert b'height="2pc"' in pdf_bytes


def test_png():
    png_bytes = base64.b64decode(
        b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQI12O'
        b'w69x7BgAE3gJRgNit0AAAAABJRU5ErkJggg==')
    png_magic_number = png_bytes[:8]

    with temp_directory() as tempdir:
        filename = os.path.join(tempdir, 'foo.png')
        filename_bytes = filename.encode(sys.getfilesystemencoding())

        surface = ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
        surface.write_to_png(filename)
        with open(filename, 'rb') as fd:
            written_png_bytes = fd.read()
            assert written_png_bytes.startswith(png_magic_number)
        open(filename, 'wb').close()
        with open(filename, 'rb') as fd:
            assert fd.read() == b''
        surface.write_to_png(filename_bytes)
        with open(filename, 'rb') as fd:
            assert fd.read() == written_png_bytes
        file_obj = io.BytesIO()
        surface.write_to_png(file_obj)
        assert file_obj.getvalue() == written_png_bytes
        assert surface.write_to_png() == written_png_bytes

        with open(filename, 'wb') as fd:
            fd.write(png_bytes)
        for source in [io.BytesIO(png_bytes), filename, filename_bytes]:
            surface = ImageSurface.create_from_png(source)
            assert surface.get_format() == cairocffi.FORMAT_ARGB32
            assert surface.get_width() == 1
            assert surface.get_height() == 1
            assert surface.get_stride() == 4
            assert surface.get_data()[:] == pixel(b'\xcc\x32\x6e\x97')

    with pytest.raises(IOError):
        # Truncated input
        surface = ImageSurface.create_from_png(io.BytesIO(png_bytes[:30]))
    with pytest.raises(IOError):
        surface = ImageSurface.create_from_png(io.BytesIO(b''))


@pytest.mark.xfail(cairo_version() < 11000,
                   reason='Cairo version too low')
def test_pdf_versions():
    assert set(PDFSurface.get_versions()) >= set([
        cairocffi.PDF_VERSION_1_4, cairocffi.PDF_VERSION_1_5])
    assert PDFSurface.version_to_string(cairocffi.PDF_VERSION_1_4) == 'PDF 1.4'
    with pytest.raises(TypeError):
        PDFSurface.version_to_string('PDF_VERSION_42')
    with pytest.raises(ValueError):
        PDFSurface.version_to_string(42)

    file_obj = io.BytesIO()
    PDFSurface(file_obj, 1, 1).finish()
    assert file_obj.getvalue().startswith((b'%PDF-1.5', b'%PDF-1.7'))

    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    surface.restrict_to_version(cairocffi.PDF_VERSION_1_4)
    surface.finish()
    assert file_obj.getvalue().startswith(b'%PDF-1.4')


def test_pdf_surface():
    with temp_directory() as tempdir:
        filename = os.path.join(tempdir, 'foo.pdf')
        filename_bytes = filename.encode(sys.getfilesystemencoding())
        file_obj = io.BytesIO()
        for target in [filename, filename_bytes, file_obj, None]:
            surface = PDFSurface(target, 123, 432)
            surface.finish()
        with open(filename, 'rb') as fd:
            assert fd.read().startswith(b'%PDF')
        with open(filename_bytes, 'rb') as fd:
            assert fd.read().startswith(b'%PDF')
        pdf = pikepdf.Pdf.open(file_obj)
        assert pdf.pages[0]['/MediaBox'] == [0, 0, 123, 432]
        assert len(pdf.pages) == 1

    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 1, 1)
    context = Context(surface)
    surface.set_size(12, 100)
    context.show_page()
    surface.set_size(42, 700)
    context.copy_page()
    surface.finish()
    pdf = pikepdf.Pdf.open(file_obj)
    assert '"/MediaBox": [ 0 0 1 1 ]' not in str(pdf.objects)
    assert pdf.pages[0]['/MediaBox'] == [0, 0, 12, 100]
    assert pdf.pages[1]['/MediaBox'] == [0, 0, 42, 700]
    assert len(pdf.pages) == 2


def test_svg_surface():
    assert set(SVGSurface.get_versions()) >= set([
        cairocffi.SVG_VERSION_1_1, cairocffi.SVG_VERSION_1_2])
    assert SVGSurface.version_to_string(cairocffi.SVG_VERSION_1_1) == 'SVG 1.1'
    with pytest.raises(TypeError):
        SVGSurface.version_to_string('SVG_VERSION_42')
    with pytest.raises(ValueError):
        SVGSurface.version_to_string(42)

    with temp_directory() as tempdir:
        filename = os.path.join(tempdir, 'foo.svg')
        filename_bytes = filename.encode(sys.getfilesystemencoding())
        file_obj = io.BytesIO()
        for target in [filename, filename_bytes, file_obj, None]:
            SVGSurface(target, 123, 432).finish()
        with open(filename, 'rb') as fd:
            assert fd.read().startswith(b'<?xml')
        with open(filename_bytes, 'rb') as fd:
            assert fd.read().startswith(b'<?xml')
        svg_bytes = file_obj.getvalue()
        assert svg_bytes.startswith(b'<?xml')
        assert b'viewBox="0 0 123 432"' in svg_bytes

    surface = SVGSurface(None, 1, 1)
    # Not obvious to test
    surface.restrict_to_version(cairocffi.SVG_VERSION_1_1)


def test_ps_surface():
    assert set(PSSurface.get_levels()) >= set([
        cairocffi.PS_LEVEL_2, cairocffi.PS_LEVEL_3])
    assert PSSurface.ps_level_to_string(cairocffi.PS_LEVEL_3) == 'PS Level 3'
    with pytest.raises(TypeError):
        PSSurface.ps_level_to_string('PS_LEVEL_42')
    with pytest.raises(ValueError):
        PSSurface.ps_level_to_string(42)

    with temp_directory() as tempdir:
        filename = os.path.join(tempdir, 'foo.ps')
        filename_bytes = filename.encode(sys.getfilesystemencoding())
        file_obj = io.BytesIO()
        for target in [filename, filename_bytes, file_obj, None]:
            PSSurface(target, 123, 432).finish()
        with open(filename, 'rb') as fd:
            assert fd.read().startswith(b'%!PS')
        with open(filename_bytes, 'rb') as fd:
            assert fd.read().startswith(b'%!PS')
        assert file_obj.getvalue().startswith(b'%!PS')

    file_obj = io.BytesIO()
    surface = PSSurface(file_obj, 1, 1)
    surface.restrict_to_level(cairocffi.PS_LEVEL_2)  # Not obvious to test
    assert surface.get_eps() is False
    surface.set_eps('lol')
    assert surface.get_eps() is True
    surface.set_eps('')
    assert surface.get_eps() is False
    surface.set_size(10, 12)
    surface.dsc_comment('%%Lorem')
    surface.dsc_begin_setup()
    surface.dsc_comment('%%ipsum')
    surface.dsc_begin_page_setup()
    surface.dsc_comment('%%dolor')
    surface.finish()
    ps_bytes = file_obj.getvalue()
    assert b'%%Lorem' in ps_bytes
    assert b'%%ipsum' in ps_bytes
    assert b'%%dolor' in ps_bytes


@pytest.mark.xfail(cairo_version() < 11000,
                   reason='Cairo version too low')
def _recording_surface_common(extents):
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 100, 100)
    empty_pixels = surface.get_data()[:]
    assert empty_pixels == b'\x00' * 40000

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 100, 100)
    context = Context(surface)
    context.move_to(20, 50)
    context.show_text('Something about us.')
    text_pixels = surface.get_data()[:]
    assert text_pixels != empty_pixels

    recording_surface = RecordingSurface(cairocffi.CONTENT_COLOR_ALPHA,
                                         extents)
    context = Context(recording_surface)
    context.move_to(20, 50)
    assert recording_surface.ink_extents() == (0, 0, 0, 0)
    context.show_text('Something about us.')
    recording_surface.flush()
    assert recording_surface.ink_extents() != (0, 0, 0, 0)

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 100, 100)
    context = Context(surface)
    context.set_source_surface(recording_surface)
    context.paint()
    recorded_pixels = surface.get_data()[:]
    return text_pixels, recorded_pixels


def test_recording_surface():
    text_pixels, recorded_pixels = _recording_surface_common((0, 0, 140, 80))
    assert recorded_pixels == text_pixels


@pytest.mark.xfail(cairo_version() < 11200,
                   reason='Cairo version too low')
def test_unbounded_recording_surface():
    text_pixels, recorded_pixels = _recording_surface_common(None)
    assert recorded_pixels == text_pixels


@pytest.mark.xfail(cairo_version() < 11200,
                   reason='Cairo version too low')
def test_recording_surface_get_extents():
    for extents in [None, (0, 0, 140, 80)]:
        surface = RecordingSurface(cairocffi.CONTENT_COLOR_ALPHA, extents)
        assert surface.get_extents() == extents


def test_matrix():
    m = Matrix()
    with pytest.raises(AttributeError):
        m.some_inexistent_attribute
    assert m.as_tuple() == (1, 0,  0, 1,  0, 0)
    m.translate(12, 4)
    assert m.as_tuple() == (1, 0,  0, 1,  12, 4)
    m.scale(2, 7)
    assert m.as_tuple() == (2, 0,  0, 7,  12, 4)
    assert m[3] == 7
    assert m.yy == 7
    m.yy = 3
    assert m.as_tuple() == (2, 0,  0, 3,  12, 4)
    assert repr(m) == 'Matrix(2, 0, 0, 3, 12, 4)'
    assert str(m) == 'Matrix(2, 0, 0, 3, 12, 4)'

    assert m.transform_distance(1, 2) == (2, 6)
    assert m.transform_point(1, 2) == (14, 10)

    m2 = m.copy()
    assert m2 == m
    m2.invert()
    assert m2.as_tuple() == (0.5, 0,  0, 1./3,  -12 / 2, -4. / 3)
    assert m.inverted() == m2
    assert m.as_tuple() == (2, 0,  0, 3,  12, 4)  # Unchanged

    m2 = Matrix(*m)
    assert m2 == m
    m2.invert()
    assert m2.as_tuple() == (0.5, 0,  0, 1./3,  -12 / 2, -4. / 3)
    assert m.inverted() == m2
    assert m.as_tuple() == (2, 0,  0, 3,  12, 4)  # Still unchanged

    m.rotate(math.pi / 2)
    assert round_tuple(m.as_tuple()) == (0, 3,  -2, 0,  12, 4)
    m *= Matrix.init_rotate(math.pi)
    assert round_tuple(m.as_tuple()) == (0, -3,  2, 0,  -12, -4)


def test_surface_pattern():
    surface = ImageSurface(cairocffi.FORMAT_A1, 1, 1)
    pattern = SurfacePattern(surface)

    surface_again = pattern.get_surface()
    assert surface_again is not surface
    assert surface_again._pointer == surface._pointer

    assert pattern.get_extend() == cairocffi.EXTEND_NONE
    pattern.set_extend(cairocffi.EXTEND_REPEAT)
    assert pattern.get_extend() == cairocffi.EXTEND_REPEAT

    assert pattern.get_filter() == cairocffi.FILTER_GOOD
    pattern.set_filter(cairocffi.FILTER_BEST)
    assert pattern.get_filter() == cairocffi.FILTER_BEST

    assert pattern.get_matrix() == Matrix()  # identity
    matrix = Matrix.init_rotate(0.5)
    pattern.set_matrix(matrix)
    assert pattern.get_matrix() == matrix
    assert pattern.get_matrix() != Matrix()


def test_solid_pattern():
    assert SolidPattern(1, .5, .25).get_rgba() == (1, .5, .25, 1)
    assert SolidPattern(1, .5, .25, .75).get_rgba() == (1, .5, .25, .75)

    surface = PDFSurface(None, 1, 1)
    context = Context(surface)
    pattern = SolidPattern(1, .5, .25)
    context.set_source(pattern)
    assert isinstance(context.get_source(), SolidPattern)
    pattern_map = cairocffi.patterns.PATTERN_TYPE_TO_CLASS
    try:
        del pattern_map[cairocffi.PATTERN_TYPE_SOLID]
        re_pattern = context.get_source()
        assert re_pattern._pointer == pattern._pointer
        assert isinstance(re_pattern, Pattern)
        assert not isinstance(re_pattern, SolidPattern)
    finally:
        pattern_map[cairocffi.PATTERN_TYPE_SOLID] = SolidPattern


def pdf_with_pattern(pattern=None):
    file_obj = io.BytesIO()
    surface = PDFSurface(file_obj, 100, 100)
    context = Context(surface)
    if pattern is not None:
        context.set_source(pattern)
    context.paint()
    surface.finish()
    return file_obj.getvalue()


def test_linear_gradient():
    gradient = LinearGradient(1, 2, 10, 20)
    assert gradient.get_linear_points() == (1, 2, 10, 20)
    gradient.add_color_stop_rgb(1, 1, .5, .25)
    gradient.add_color_stop_rgb(offset=.5, red=1, green=.5, blue=.25)
    gradient.add_color_stop_rgba(.5, 1, .5, .75, .25)
    assert gradient.get_color_stops() == [
        (.5, 1, .5, .25, 1),
        (.5, 1, .5, .75, .25),
        (1, 1, .5, .25, 1)]

    # Values chosen so that we can test get_data() bellow with an exact
    # byte string that (hopefully) does not depend on rounding behavior:
    # 255 / 5. == 51.0 == 0x33
    surface = ImageSurface(cairocffi.FORMAT_A8, 8, 4)
    assert surface.get_data()[:] == b'\x00' * 32
    gradient = LinearGradient(1.5, 0, 6.5, 0)
    gradient.add_color_stop_rgba(0, 0, 0, 0, 0)
    gradient.add_color_stop_rgba(1, 0, 0, 0, 1)
    context = Context(surface)
    context.set_source(gradient)
    context.paint()
    assert surface.get_data()[:] == b'\x00\x00\x33\x66\x99\xCC\xFF\xFF' * 4

    assert b'/ShadingType 2' not in pdf_with_pattern()
    assert b'/ShadingType 2' in pdf_with_pattern(gradient)


def test_radial_gradient():
    gradient = RadialGradient(42, 420, 10, 43, 430, 100)
    assert gradient.get_radial_circles() == (42, 420, 10, 43, 430, 100)
    gradient.add_color_stop_rgb(1, 1, .5, .25)
    gradient.add_color_stop_rgb(offset=.5, red=1, green=.5, blue=.25)
    gradient.add_color_stop_rgba(.5, 1, .5, .75, .25)
    assert gradient.get_color_stops() == [
        (.5, 1, .5, .25, 1),
        (.5, 1, .5, .75, .25),
        (1, 1, .5, .25, 1)]

    assert b'/ShadingType 3' not in pdf_with_pattern()
    assert b'/ShadingType 3' in pdf_with_pattern(gradient)


def test_context_as_context_manager():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
    context = Context(surface)
    # The default source is opaque black:
    assert context.get_source().get_rgba() == (0, 0, 0, 1)
    with context:
        context.set_source_rgb(1, .25, .5)
        assert context.get_source().get_rgba() == (1, .25, .5, 1)
    # Context restored at the end of with statement.
    assert context.get_source().get_rgba() == (0, 0, 0, 1)
    try:
        with context:
            context.set_source_rgba(1, .25, .75, .5)
            assert context.get_source().get_rgba() == (1, .25, .75, .5)
            raise ValueError
    except ValueError:
        pass
    # Context also restored on exceptions.
    assert context.get_source().get_rgba() == (0, 0, 0, 1)


def test_context_groups():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
    context = Context(surface)
    assert isinstance(context.get_target(), ImageSurface)
    assert context.get_target()._pointer == surface._pointer
    assert context.get_group_target()._pointer == surface._pointer
    assert (context.get_group_target().get_content() ==
            cairocffi.CONTENT_COLOR_ALPHA)
    assert surface.get_data()[:] == pixel(b'\x00\x00\x00\x00')

    with context:
        context.push_group_with_content(cairocffi.CONTENT_ALPHA)
        assert (context.get_group_target().get_content() ==
                cairocffi.CONTENT_ALPHA)
        context.set_source_rgba(1, .2, .4, .8)  # Only A is actually used
        assert isinstance(context.get_source(), SolidPattern)
        context.paint()
        context.pop_group_to_source()
        assert isinstance(context.get_source(), SurfacePattern)
        # Still nothing on the original surface
        assert surface.get_data()[:] == pixel(b'\x00\x00\x00\x00')
        context.paint()
        assert surface.get_data()[:] == pixel(b'\xCC\x00\x00\x00')

    with context:
        context.push_group()
        context.set_source_rgba(1, .2, .4)
        context.paint()
        group = context.pop_group()
        assert isinstance(context.get_source(), SolidPattern)
        assert isinstance(group, SurfacePattern)
        context.set_source_surface(group.get_surface())
        assert surface.get_data()[:] == pixel(b'\xCC\x00\x00\x00')
        context.paint()
        assert surface.get_data()[:] == pixel(b'\xFF\xFF\x33\x66')


def test_context_current_transform_matrix():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
    context = Context(surface)
    assert isinstance(context.get_matrix(), Matrix)
    assert context.get_matrix().as_tuple() == (1, 0, 0, 1, 0, 0)
    context.translate(6, 5)
    assert context.get_matrix().as_tuple() == (1, 0, 0, 1, 6, 5)
    context.scale(1, 6)
    assert context.get_matrix().as_tuple() == (1, 0, 0, 6, 6, 5)
    context.scale(.5)
    assert context.get_matrix().as_tuple() == (.5, 0, 0, 3, 6, 5)
    context.rotate(math.pi / 2)
    assert round_tuple(context.get_matrix().as_tuple()) == (0, 3, -.5, 0, 6, 5)

    context.identity_matrix()
    assert context.get_matrix().as_tuple() == (1, 0, 0, 1, 0, 0)
    context.set_matrix(Matrix(2, 1, 3, 7, 8, 2))
    assert context.get_matrix().as_tuple() == (2, 1, 3, 7, 8, 2)
    context.transform(Matrix(2, 0, 0, .5, 0, 0))
    assert context.get_matrix().as_tuple() == (4, 2, 1.5, 3.5, 8, 2)

    context.set_matrix(Matrix(2, 0,  0, 3,  12, 4))
    assert context.user_to_device_distance(1, 2) == (2, 6)
    assert context.user_to_device(1, 2) == (14, 10)
    assert context.device_to_user_distance(2, 6) == (1, 2)
    assert round_tuple(context.device_to_user(14, 10)) == (1, 2)


def test_context_path():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
    context = Context(surface)

    assert context.copy_path() == []
    assert context.has_current_point() is False
    assert context.get_current_point() == (0, 0)
    context.arc(100, 200, 20, math.pi/2, 0)
    path_1 = context.copy_path()
    assert path_1[0] == (cairocffi.PATH_MOVE_TO, (100, 220))
    assert len(path_1) > 1
    assert all(part[0] == cairocffi.PATH_CURVE_TO for part in path_1[1:])
    assert context.has_current_point() is True
    assert context.get_current_point() == (120, 200)

    context.new_sub_path()
    assert context.copy_path() == path_1
    assert context.has_current_point() is False
    assert context.get_current_point() == (0, 0)
    context.new_path()
    assert context.copy_path() == []
    assert context.has_current_point() is False
    assert context.get_current_point() == (0, 0)

    context.arc_negative(100, 200, 20, math.pi/2, 0)
    path_2 = context.copy_path()
    assert path_2[0] == (cairocffi.PATH_MOVE_TO, (100, 220))
    assert len(path_2) > 1
    assert all(part[0] == cairocffi.PATH_CURVE_TO for part in path_2[1:])
    assert path_2 != path_1

    context.new_path()
    context.rectangle(10, 20, 100, 200)
    path = context.copy_path()
    # Some cairo versions add a MOVE_TO after a CLOSE_PATH
    if path[-1] == (cairocffi.PATH_MOVE_TO, (10, 20)):  # pragma: no cover
        path = path[:-1]
    assert path == [
        (cairocffi.PATH_MOVE_TO, (10, 20)),
        (cairocffi.PATH_LINE_TO, (110, 20)),
        (cairocffi.PATH_LINE_TO, (110, 220)),
        (cairocffi.PATH_LINE_TO, (10, 220)),
        (cairocffi.PATH_CLOSE_PATH, ())]
    assert context.path_extents() == (10, 20, 110, 220)

    context.new_path()
    context.move_to(10, 20)
    context.line_to(10, 30)
    context.rel_move_to(2, 5)
    context.rel_line_to(2, 5)
    context.curve_to(20, 30, 70, 50, 100, 120)
    context.rel_curve_to(20, 30, 70, 50, 100, 120)
    context.close_path()
    path = context.copy_path()
    if path[-1] == (cairocffi.PATH_MOVE_TO, (12, 35)):  # pragma: no cover
        path = path[:-1]
    assert path == [
        (cairocffi.PATH_MOVE_TO, (10, 20)),
        (cairocffi.PATH_LINE_TO, (10, 30)),
        (cairocffi.PATH_MOVE_TO, (12, 35)),
        (cairocffi.PATH_LINE_TO, (14, 40)),
        (cairocffi.PATH_CURVE_TO, (20, 30, 70, 50, 100, 120)),
        (cairocffi.PATH_CURVE_TO, (120, 150, 170, 170, 200, 240)),
        (cairocffi.PATH_CLOSE_PATH, ())]

    context.new_path()
    context.move_to(10, 15)
    context.curve_to(20, 30, 70, 50, 100, 120)
    assert context.copy_path() == [
        (cairocffi.PATH_MOVE_TO, (10, 15)),
        (cairocffi.PATH_CURVE_TO, (20, 30, 70, 50, 100, 120))]
    path = context.copy_path_flat()
    assert len(path) > 2
    assert path[0] == (cairocffi.PATH_MOVE_TO, (10, 15))
    assert all(part[0] == cairocffi.PATH_LINE_TO for part in path[1:])
    assert path[-1] == (cairocffi.PATH_LINE_TO, (100, 120))

    context.new_path()
    context.move_to(10, 20)
    context.line_to(10, 30)
    path = context.copy_path()
    assert path == [
        (cairocffi.PATH_MOVE_TO, (10, 20)),
        (cairocffi.PATH_LINE_TO, (10, 30))]
    additional_path = [(cairocffi.PATH_LINE_TO, (30, 150))]
    context.append_path(additional_path)
    assert context.copy_path() == path + additional_path
    # Incorrect number of points:
    with pytest.raises(ValueError):
        context.append_path([(cairocffi.PATH_LINE_TO, (30, 150, 1))])
    with pytest.raises(ValueError):
        context.append_path([(cairocffi.PATH_LINE_TO, (30, 150, 1, 4))])


def test_context_properties():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
    context = Context(surface)

    assert context.get_antialias() == cairocffi.ANTIALIAS_DEFAULT
    context.set_antialias(cairocffi.ANTIALIAS_BEST)
    assert context.get_antialias() == cairocffi.ANTIALIAS_BEST

    assert context.get_dash() == ([], 0)
    context.set_dash([4, 1, 3, 2], 1.5)
    assert context.get_dash() == ([4, 1, 3, 2], 1.5)
    assert context.get_dash_count() == 4

    assert context.get_fill_rule() == cairocffi.FILL_RULE_WINDING
    context.set_fill_rule(cairocffi.FILL_RULE_EVEN_ODD)
    assert context.get_fill_rule() == cairocffi.FILL_RULE_EVEN_ODD

    assert context.get_line_cap() == cairocffi.LINE_CAP_BUTT
    context.set_line_cap(cairocffi.LINE_CAP_SQUARE)
    assert context.get_line_cap() == cairocffi.LINE_CAP_SQUARE

    assert context.get_line_join() == cairocffi.LINE_JOIN_MITER
    context.set_line_join(cairocffi.LINE_JOIN_ROUND)
    assert context.get_line_join() == cairocffi.LINE_JOIN_ROUND

    assert context.get_line_width() == 2
    context.set_line_width(13)
    assert context.get_line_width() == 13

    assert context.get_miter_limit() == 10
    context.set_miter_limit(4)
    assert context.get_miter_limit() == 4

    assert context.get_operator() == cairocffi.OPERATOR_OVER
    context.set_operator(cairocffi.OPERATOR_XOR)
    assert context.get_operator() == cairocffi.OPERATOR_XOR

    assert context.get_tolerance() == 0.1
    context.set_tolerance(0.25)
    assert context.get_tolerance() == 0.25


def test_context_fill():
    surface = ImageSurface(cairocffi.FORMAT_A8, 4, 4)
    assert surface.get_data()[:] == b'\x00' * 16
    context = Context(surface)
    context.set_source_rgba(0, 0, 0, .5)
    context.set_line_width(.5)
    context.rectangle(1, 1, 2, 2)
    assert context.fill_extents() == (1, 1, 3, 3)
    assert context.stroke_extents() == (.75, .75, 3.25, 3.25)
    assert context.in_fill(2, 2) is True
    assert context.in_fill(.8, 2) is False
    assert context.in_stroke(2, 2) is False
    assert context.in_stroke(.8, 2) is True
    path = list(context.copy_path())
    assert path
    context.fill_preserve()
    assert list(context.copy_path()) == path
    assert surface.get_data()[:] == (
        b'\x00\x00\x00\x00'
        b'\x00\x80\x80\x00'
        b'\x00\x80\x80\x00'
        b'\x00\x00\x00\x00'
    )
    context.fill()
    assert list(context.copy_path()) == []
    assert surface.get_data()[:] == (
        b'\x00\x00\x00\x00'
        b'\x00\xC0\xC0\x00'
        b'\x00\xC0\xC0\x00'
        b'\x00\x00\x00\x00'
    )


def test_context_stroke():
    for preserve in [True, False]:
        surface = ImageSurface(cairocffi.FORMAT_A8, 4, 4)
        assert surface.get_data()[:] == b'\x00' * 16
        context = Context(surface)
        context.set_source_rgba(0, 0, 0, 1)
        context.set_line_width(1)
        context.rectangle(.5, .5, 2, 2)
        path = list(context.copy_path())
        assert path
        context.stroke_preserve() if preserve else context.stroke()
        assert list(context.copy_path()) == (path if preserve else [])
        assert surface.get_data()[:] == (
            b'\xFF\xFF\xFF\x00'
            b'\xFF\x00\xFF\x00'
            b'\xFF\xFF\xFF\x00'
            b'\x00\x00\x00\x00')


def test_context_clip():
    surface = ImageSurface(cairocffi.FORMAT_A8, 4, 4)
    assert surface.get_data()[:] == b'\x00' * 16
    context = Context(surface)
    context.rectangle(1, 1, 2, 2)
    assert context.clip_extents() == (0, 0, 4, 4)
    path = list(context.copy_path())
    assert path
    context.clip_preserve()
    assert list(context.copy_path()) == path
    assert context.clip_extents() == (1, 1, 3, 3)
    context.clip()
    assert list(context.copy_path()) == []
    assert context.clip_extents() == (1, 1, 3, 3)
    context.reset_clip()
    assert context.clip_extents() == (0, 0, 4, 4)

    context.rectangle(1, 1, 2, 2)
    context.rectangle(1, 2, 1, 2)
    context.clip()
    assert context.copy_clip_rectangle_list() == [(1, 1, 2, 2), (1, 3, 1, 1)]
    assert context.clip_extents() == (1, 1, 3, 4)


@pytest.mark.xfail(cairo_version() < 11000,
                   reason='Cairo version too low')
def test_context_in_clip():
    surface = ImageSurface(cairocffi.FORMAT_A8, 4, 4)
    context = Context(surface)
    context.rectangle(1, 1, 2, 2)
    assert context.in_clip(.5, 2) is True
    assert context.in_clip(1.5, 2) is True
    context.clip()
    assert context.in_clip(.5, 2) is False
    assert context.in_clip(1.5, 2) is True


def test_context_mask():
    mask_surface = ImageSurface(cairocffi.FORMAT_ARGB32, 2, 2)
    context = Context(mask_surface)
    context.set_source_rgba(1, 0, .5, 1)
    context.rectangle(0, 0, 1, 1)
    context.fill()
    context.set_source_rgba(1, .5, 1, .5)
    context.rectangle(1, 1, 1, 1)
    context.fill()

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 4, 4)
    context = Context(surface)
    context.mask(SurfacePattern(mask_surface))
    o = pixel(b'\x00\x00\x00\x00')
    b = pixel(b'\x80\x00\x00\x00')
    B = pixel(b'\xFF\x00\x00\x00')
    assert surface.get_data()[:] == (
        B + o + o + o +
        o + b + o + o +
        o + o + o + o +
        o + o + o + o
    )

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 4, 4)
    context = Context(surface)
    context.mask_surface(mask_surface, surface_x=1, surface_y=2)
    o = pixel(b'\x00\x00\x00\x00')
    b = pixel(b'\x80\x00\x00\x00')
    B = pixel(b'\xFF\x00\x00\x00')
    assert surface.get_data()[:] == (
        o + o + o + o +
        o + o + o + o +
        o + B + o + o +
        o + o + b + o
    )


def test_context_font():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 10, 10)
    context = Context._from_pointer(Context(surface)._pointer, incref=True)
    assert context.get_font_matrix().as_tuple() == (10, 0, 0, 10, 0, 0)
    context.set_font_matrix(Matrix(2, 0,  0, 3,  12, 4))
    assert context.get_font_matrix().as_tuple() == (2, 0,  0, 3,  12, 4)
    context.set_font_size(14)
    assert context.get_font_matrix().as_tuple() == (14, 0, 0, 14, 0, 0)

    context.set_font_size(10)
    context.select_font_face(b'@cairo:serif', cairocffi.FONT_SLANT_ITALIC)
    font_face = context.get_font_face()
    assert isinstance(font_face, ToyFontFace)
    assert font_face.get_family() == '@cairo:serif'
    assert font_face.get_slant() == cairocffi.FONT_SLANT_ITALIC
    assert font_face.get_weight() == cairocffi.FONT_WEIGHT_NORMAL

    try:
        del cairocffi.fonts.FONT_TYPE_TO_CLASS[cairocffi.FONT_TYPE_TOY]
        re_font_face = context.get_font_face()
        assert re_font_face._pointer == font_face._pointer
        assert isinstance(re_font_face, FontFace)
        assert not isinstance(re_font_face, ToyFontFace)
    finally:
        cairocffi.fonts.FONT_TYPE_TO_CLASS[cairocffi.FONT_TYPE_TOY] = \
            ToyFontFace

    ascent, descent, height, max_x_advance, max_y_advance = (
        context.font_extents())
    # That’s about all we can assume for a default font.
    assert max_x_advance > 0
    assert max_y_advance == 0
    _, _, _, _, x_advance, y_advance = context.text_extents('i' * 10)
    assert x_advance > 0
    assert y_advance == 0
    context.set_font_face(
        ToyFontFace('@cairo:monospace', weight=cairocffi.FONT_WEIGHT_BOLD))
    _, _, _, _, x_advance_mono, y_advance = context.text_extents('i' * 10)
    assert x_advance_mono > x_advance
    assert y_advance == 0
    assert list(context.copy_path()) == []
    context.text_path('a')
    assert list(context.copy_path())
    assert surface.get_data()[:] == b'\x00' * 400
    context.move_to(1, 9)
    context.show_text('a')
    assert surface.get_data()[:] != b'\x00' * 400

    assert (context.get_font_options().get_hint_metrics() ==
            cairocffi.HINT_METRICS_DEFAULT)
    context.set_font_options(
        FontOptions(hint_metrics=cairocffi.HINT_METRICS_ON))
    assert (context.get_font_options().get_hint_metrics() ==
            cairocffi.HINT_METRICS_ON)
    assert (surface.get_font_options().get_hint_metrics() ==
            cairocffi.HINT_METRICS_ON)

    context.set_font_matrix(Matrix(2, 0,  0, 3,  12, 4))
    assert context.get_scaled_font().get_font_matrix().as_tuple() == (
        2, 0,  0, 3,  12, 4)
    context.set_scaled_font(ScaledFont(ToyFontFace(), font_matrix=Matrix(
        0, 1,  4, 0,  12, 4)))
    assert context.get_font_matrix().as_tuple() == (0, 1,  4, 0,  12, 4)

    # Reset the default
    context.set_font_face(None)
    # TODO: test this somehow.


def test_scaled_font():
    font = ScaledFont(ToyFontFace())
    font_extents = font.extents()
    ascent, descent, height, max_x_advance, max_y_advance = font_extents
    assert max_x_advance > 0
    assert max_y_advance == 0
    _, _, _, _, x_advance, y_advance = font.text_extents('i' * 10)
    assert x_advance > 0
    assert y_advance == 0

    font = ScaledFont(ToyFontFace('@cairo:serif'))
    _, _, _, _, x_advance, y_advance = font.text_extents('i' * 10)

    font = ScaledFont(ToyFontFace('@cairo:monospace'))
    _, _, _, _, x_advance_mono, y_advance = font.text_extents('i' * 10)
    assert x_advance_mono > x_advance
    assert y_advance == 0
    # Not much we can test:
    # The toy font face was "materialized" into a specific backend.
    assert isinstance(font.get_font_face(), FontFace)

    font = ScaledFont(
        ToyFontFace('@cairo:monospace'),
        Matrix(xx=20, yy=20), Matrix(xx=3, yy=.5),
        FontOptions(antialias=cairocffi.ANTIALIAS_BEST))
    assert font.get_font_options().get_antialias() == cairocffi.ANTIALIAS_BEST
    assert font.get_font_matrix().as_tuple() == (20, 0, 0, 20, 0, 0)
    assert font.get_ctm().as_tuple() == (3, 0, 0, .5, 0, 0)
    assert font.get_scale_matrix().as_tuple() == (60, 0, 0, 10, 0, 0)
    _, _, _, _, x_advance_mono_2, y_advance_2 = font.text_extents('i' * 10)
    # Same yy as before:
    assert y_advance == y_advance_2
    # Bigger xx:
    assert x_advance_mono_2 > x_advance_mono


def test_font_options():
    options = FontOptions()

    assert options.get_antialias() == cairocffi.ANTIALIAS_DEFAULT
    options.set_antialias(cairocffi.ANTIALIAS_FAST)
    assert options.get_antialias() == cairocffi.ANTIALIAS_FAST

    assert options.get_subpixel_order() == cairocffi.SUBPIXEL_ORDER_DEFAULT
    options.set_subpixel_order(cairocffi.SUBPIXEL_ORDER_BGR)
    assert options.get_subpixel_order() == cairocffi.SUBPIXEL_ORDER_BGR

    assert options.get_hint_style() == cairocffi.HINT_STYLE_DEFAULT
    options.set_hint_style(cairocffi.HINT_STYLE_SLIGHT)
    assert options.get_hint_style() == cairocffi.HINT_STYLE_SLIGHT

    assert options.get_hint_metrics() == cairocffi.HINT_METRICS_DEFAULT
    options.set_hint_metrics(cairocffi.HINT_METRICS_OFF)
    assert options.get_hint_metrics() == cairocffi.HINT_METRICS_OFF

    options_1 = FontOptions(hint_metrics=cairocffi.HINT_METRICS_ON)
    assert options_1.get_hint_metrics() == cairocffi.HINT_METRICS_ON
    assert options_1.get_antialias() == cairocffi.HINT_METRICS_DEFAULT
    options_2 = options_1.copy()
    assert options_2 == options_1
    assert len(set([options_1, options_2])) == 1  # test __hash__
    options_2.set_antialias(cairocffi.ANTIALIAS_BEST)
    assert options_2 != options_1
    assert len(set([options_1, options_2])) == 2
    options_1.merge(options_2)
    assert options_2 == options_1


@pytest.mark.xfail(cairo_version() < 11512,
                   reason='Cairo version too low')
def test_font_options_variations():
    options = FontOptions()

    assert options.get_variations() is None
    options.set_variations('wght 400, wdth 300')
    assert options.get_variations() == 'wght 400, wdth 300'
    options.set_variations(None)
    assert options.get_variations() is None


def test_glyphs():
    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 100, 20)
    context = Context(surface)
    font = context.get_scaled_font()
    text = 'Étt'
    glyphs, clusters, is_backwards = font.text_to_glyphs(
        5, 15, text, with_clusters=True)
    assert font.text_to_glyphs(5, 15, text, with_clusters=False) == glyphs
    (idx1, x1, y1), (idx2, x2, y2), (idx3, x3, y3) = glyphs
    assert idx1 != idx2 == idx3
    assert y1 == y2 == y3 == 15
    assert 5 == x1 < x2 < x3
    assert clusters == [(2, 1), (1, 1), (1, 1)]
    assert is_backwards == 0
    assert round_tuple(font.glyph_extents(glyphs)) == (
        round_tuple(font.text_extents(text)))
    assert round_tuple(font.glyph_extents(glyphs)) == (
        round_tuple(context.glyph_extents(glyphs)))

    assert context.copy_path() == []
    context.glyph_path(glyphs)
    glyph_path = context.copy_path()
    assert glyph_path
    context.new_path()
    assert context.copy_path() == []
    context.move_to(10, 20)  # Not the same coordinates as text_to_glyphs
    context.text_path(text)
    assert context.copy_path() != []
    assert context.copy_path() != glyph_path
    context.new_path()
    assert context.copy_path() == []
    context.move_to(5, 15)
    context.text_path(text)
    text_path = context.copy_path()
    # For some reason, paths end with a different on old cairo.
    assert text_path[:-1] == glyph_path[:-1]

    empty = b'\x00' * 100 * 20 * 4
    assert surface.get_data()[:] == empty
    context.show_glyphs(glyphs)
    glyph_pixels = surface.get_data()[:]
    assert glyph_pixels != empty

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 100, 20)
    context = Context(surface)
    context.move_to(5, 15)
    context.show_text_glyphs(text, glyphs, clusters, is_backwards)
    text_glyphs_pixels = surface.get_data()[:]
    assert glyph_pixels == text_glyphs_pixels

    surface = ImageSurface(cairocffi.FORMAT_ARGB32, 100, 20)
    context = Context(surface)
    context.move_to(5, 15)
    context.show_text(text)
    text_pixels = surface.get_data()[:]
    assert glyph_pixels == text_pixels


def test_from_null_pointer():
    for class_ in [Surface, Context, Pattern, FontFace, ScaledFont]:
        with pytest.raises(ValueError):
            class_._from_pointer(cairocffi.ffi.NULL, 'unused')
