#!/usr/bin/python3
# -*- coding: utf-8 -*-
import vapoursynth as vs
from vapoursynth import core
from vsrgtools import remove_grain
from vsexprtools import norm_expr
from vskernels import Bilinear, Blackman, Descaler, Kernel
from vstools import depth, DitherType, scale_value, Range
from enum import StrEnum

def get_scale_offsets(scaled_w, scaled_h, origin_w, origin_h,
					  offset_l, offset_t, offset_w, offset_h):
	"""
Inverts scaling offsets (kind of like inverting the scaling itself, really).

Calculates the scale offsets necessary to scale back to its original form an
image that was scaled to the specified dimensions using the specified offsets.
	"""
	# input parameters
	scaled = [scaled_w, scaled_h]
	origin = [origin_w, origin_h]
	scaled_off = [offset_l, offset_t, offset_w, offset_h]

	# source offsets, from lengths (w / h) to crop-style (negative values)
	for i, (org_l, off_l) in enumerate(zip(origin, scaled_off[:2]), 2):
		# If the input is positive, it represents a length, rather than a crop-
		# style offset from the bottom right. Even if the output from this code
		# is positive, however, it must always be a crop-style offset, so there
		# won't be any special treatment required.
		if scaled_off[i] > 0:
			scaled_off[i] -= org_l - off_l

	# the actual scaling of the offsets
	scales = 2 * [scale / original for original, scale in zip(origin, scaled)]
	off = [-offset * scale for offset, scale in zip(scaled_off, scales * 2)]

	# target offsets, from crop-style to lengths
	for i, (scaled_l, off_l) in enumerate(zip(scaled, off[:2]), 2):
		# The input must be a crop-style offset from the bottom right, even if
		# it happens to be positive. I could process only the positive values,
		# but because I like consistency, I decided to convert all values from
		# crop-style offsets to represent a length, regardless of whether it's
		# really necessary.
		off[i] += scaled_l - off_l

	return tuple(off)

class Mode(StrEnum):
	Normal = "normal"
	Lowpass = "lowpass"
	Lowpass_PCLevels = "lowpasspc"
	PCLevels = "pclevels"

def MaskDetail(clip: vs.VideoNode,\
			   final_width: int, final_height: int,\
			   RGmode: remove_grain.Mode=remove_grain.Mode.MINMAX_AROUND3,\
			   cutoff: float | int=0.275, gain: float=0.75, expandN: int=2, inflateN: int=1, blur_more: bool=False,
			   kernel: Descaler=Bilinear,
			   mode=Mode.Normal, lowpasskernel: Kernel=Blackman, lowpassthr: int | None=None, exportlowpass: bool=False, pclevelthr: int | None=None)\
			   -> vs.VideoNode:
	if   type(cutoff) == int:
		intCutoff = int(scale_value(cutoff, clip.format, vs.GRAY16, Range.FULL, Range.FULL))
	elif type(cutoff) == float:
		intCutoff = int(scale_value(cutoff, vs.GRAYS, vs.GRAY16, Range.FULL, Range.FULL))

	if lowpassthr is None:
		lowpassthr = 1542
	else:
		lowpassthr = int(scale_value(lowpassthr, clip.format, vs.GRAY16, Range.FULL, Range.FULL))

	if pclevelthr is None:
		pclevelthr = 59881
	else:
		pclevelthr = int(scale_value(pclevelthr, clip.format, vs.GRAY16, Range.FULL, Range.FULL))

	histluma16 = f"range_max 1 + 16 / 1 - rpa! range_min 16 rpa@ x range_min - rpa@ 2 * % rpa@ - abs - * +"

	startclip = depth(clip, 16, dither_type=DitherType.ROUND)

	if mode in [Mode.Lowpass, Mode.Lowpass_PCLevels]:
		lowpass = lowpasskernel().scale(startclip, startclip.width*2, startclip.height*2)
		lowpass = lowpasskernel().scale(lowpass, startclip.width, startclip.height)

		difflow = core.std.MakeDiff(startclip, lowpass, 0)
		if exportlowpass:
			return norm_expr(difflow, histluma16)

		difflow = remove_grain(difflow, mode=[remove_grain.Mode.MINMAX_AROUND1])
		difflow = norm_expr(difflow, " ".join([f"x neutral - p!", 
                                               f"p@ 0  > p@ {lowpassthr} - 0 > and x {lowpassthr} -",
                                               f"p@ 0 <= p@ {lowpassthr} + 0 < and x {lowpassthr} +",
                                               f"neutral",
                                               f"? ?"]))

		startclip = core.std.MergeDiff(startclip, difflow, 0)

	if mode in [Mode.PCLevels, Mode.Lowpass_PCLevels]:
		diff = norm_expr(clip, f"x {pclevelthr} > x range_min ?")
	else:
		temp = depth(startclip, 32)
		temp = kernel().descale(temp, final_width, final_height)
		temp = kernel().scale(temp, startclip.width, startclip.height)
		diff = core.std.MakeDiff(startclip, depth(temp, 16, dither_type=DitherType.ROUND), 0)

	mask = remove_grain(norm_expr(diff, histluma16), RGmode)
	mask = norm_expr(mask, f"x {intCutoff} < 0 x {gain} range_max x + range_max / * * ?")

	for i in range(expandN):
		mask = core.std.Maximum(mask, planes=[0])
	for i in range(inflateN):
		mask = core.std.Inflate(mask, planes=[0])

	mask = Bilinear().scale(mask, final_width, final_height)
	if blur_more:
		mask = remove_grain(mask, mode=[remove_grain.Mode.BINOMIAL_BLUR, remove_grain.Mode.NONE, remove_grain.Mode.NONE])

	mask = core.std.ShufflePlanes(mask, planes=0, colorfamily=vs.GRAY)
	return depth(mask, clip.format.bits_per_sample, dither_type=DitherType.ROUND, range_in=vs.RANGE_FULL, range_out=vs.RANGE_FULL)
