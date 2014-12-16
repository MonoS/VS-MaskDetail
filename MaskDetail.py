#!/usr/bin/python3
# -*- coding: utf-8 -*-

import vapoursynth as vs
import functools
# TODO if those functions are only needed internally, then functools isn't needed
#      as they can just be def'd inside maskDetail, using its parameters

def f16(x, cutoff=17990, gain=0.75):
    if x < cutoff:
        return 0

    result = x * gain * (0x10000 + x) / 0x10000
    return min(0xFFFF, int(result))

def luma16(x):
    x <<= 4
    value = x & 0xFFFF
    return 0xFFFF - value if x & 0x10000 else value

def lowpassLut16(x, threshold=1542):
    p = x - 0x8000
    if p > 0 and p - threshold > 0:
        return x - threshold
    elif p <= 0 and p + threshold < 0:
        return x + threshold
    else:
        return 0x8000

def pclevelLut16(x, threshold=59881):
    return x if x > threshold else 0

def maskDetail(clip, final_width, final_height, RGmode=3, cutoff=None,
               gain=0.75, expandN=2, inflateN=1, blur_more=False,
               src_left=0, src_top=0, src_width=0, src_height=0,
               kernel='bilinear', invkstaps=4, taps=4, mode='normal',
               lowpasskernel='blackman', lowpassintaps=4, lowpassouttaps=3,
               lowpassthr=None, exportlowpass=False, pclevelthr=None):
    depth = clip.format.bits_per_sample
    # I removed the restriction to only 8 or 16 bit clips
    # TODO is this correct?
    scale = (2 ** 16 - 1) / (2 ** depth - 1)

    if cutoff is None:
        cutoff = 17990
    else:
        cutoff *= scale

    if lowpassthr is None:
        lowpassthr = 1542
    else:
        lowpassthr *= scale

    if pclevelthr is None:
        pclevelthr = 17990
    else:
        pclevelthr *= scale

    core = vs.get_core()

    startclip = core.fmtc.bitdepth(clip, bits=16)
    original = (startclip.width, startclip.height)
    target = (final_width, final_height, src_left, src_top, src_width, src_height)

    if mode.startswith('lowpass'): # lowpass and lowpasspc
        twice = tuple(2 * o for o in original)
        lowpass = core.fmtc.resample(startclip, *twice, kernel=lowpasskernel,
                                     taps=lowpassintaps)
        # I gathered that you wanted to apply the second resample
        # on the lowpass clip rather than also applying it on startclip
        lowpass = core.fmtc.resample(lowpass, *original, kernel=lowpasskernel,
                                     taps=lowpassouttaps)
        if exportlowpass:
            return core.std.MakeDiff(startclip, lowpass, 0).std.Lut(function=luma16)

        # I changed RemoveGrain([1]) to RemoveGrain(mode=[1])
        difflow = core.std.MakeDiff(startclip, lowpass, 0).rgvs.RemoveGrain(mode=[1])
        difflow = core.std.Lut(difflow, functools.partial(lowpassLut16,
                                                          threshold=lowpassthr))

        startclip = core.std.MergeDiff(startclip, difflow, 0)

    if mode.startswith('pc') or mode.endswith('pc'): # pclevel and lowpasspc
        diff = core.std.Lut(startclip, function=functools.partial(pclevelLut16,
                                                                  threshold=pclevelthr))
    else:
        temp = core.fmtc.resample(startclip, *target[:2], kernel=kernel,
                                  invks=True, invkstaps=invkstaps, taps=taps)
        temp = core.fmtc.resample(temp, *original, kernel=kernel, taps=taps)
        diff = core.std.MakeDiff(startclip, temp, 0)

    mask = core.std.Lut(diff, function=luma16).rgvs.RemoveGrain(mode=[RGmode])
    mask = core.std.Lut(mask, function=functools.partial(f16, cutoff=cutoff,
                                                         gain=gain))

    for i in range(expandN):
        mask = core.generic.Maximum(mask, planes=[0])
    for i in range(inflateN):
        mask = core.generic.Inflate(mask, planes=[0])

    mask = core.fmtc.resample(mask, *target, taps=taps)
    if blur_more:
        mask = core.rgvs.RemoveGrain(mask, mode=[12,0,0])

    mask = core.std.ShufflePlanes(mask, planes=0, colorfamily=vs.GRAY)
    return core.fmtc.bitdepth(mask, bits=depth, mode=1)
