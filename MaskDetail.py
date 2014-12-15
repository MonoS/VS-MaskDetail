import vapoursynth as vs

class InvalidArgument(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value) 

class MonoS(object):
	Gcutoff = 17990
	Ggain = 0.75
	Glowpassthr = 1542
	Gpclevelthr = 59881
	
	def f16(x):
		if (x < Gcutoff):
			return 0
		else:
			result = int(float(x) * Ggain * ((0xFFFF+1)+x) / (0xFFFF+1))
			if result > 0xFFFF:
				return 0xFFFF
			else:
				return result
	
	def Luma16(x):
		p = x << 4
		if (p & (0xffff + 1)):
			return (0xffff - (p&0xffff))
		else:
			return p&0xffff
	
	def LowPassLUT16(x):
		p = x - 0x8000
		if (p > 0):
			if (p - Glowpassthr > 0):
				return x - Glowpassthr
			else:
				return 0x8000
		else:
			if (p + Glowpassthr < 0):
				return x + Glowpassthr
			else:
				return 0x8000
	
	def PCLevelLUT16(x):
		if (x > Gpclevelthr):
			return x
		else:
			return 0
	
	def MaskDetail(clip, final_width, final_height, RGmode=3, cutoff=-1, gain=0.75, expandN=2, inflateN=1, blur_more=False, src_left=0, src_top=0, src_width=0, src_height=0, kernel="bilinear", invkstaps = 4, taps=4, mode="normal", lowpasskernel="blackman", lowpassintaps=4, lowpassouttaps=3, lowpassthr=-1, exportlowpass=False, pclevelthr=-1):
		
		core = vs.get_core()		
		
		if ((clip.format.bits_per_sample == 8) or (clip.format.bits_per_sample == 16)):
			if (clip.format.bits_per_sample == 8):
				if cutoff == -1:
					cutoff = 17990
				else:
					cutoff = cutoff * 65535/255
				
				if lowpassthr == -1:
					lowpassthr = 1542
				else:
					lowpassthr = lowpassthr * 65535/255
				
				if pclevelthr == -1:
					pclevelthr = 59881
				else:
					pclevelthr = pclevelthr * 65535/255
					
				
				startclip = core.fmtc.bitdepth(clip, bits=16)
			else:
				if cutoff == -1:
					cutoff = 17990
				
				if lowpassthr == -1:
					lowpassthr = 1542

				if pclevelthr == -1:
					pclevelthr = 59881				
				
				startclip = clip
		else:
			raise InvalidArgument('Input clip must be 8 or 16 bit')
		
		global Gcutoff
		global Ggain
		global Glowpassthr
		global Gpclevelthr
		Ggain = gain
		Gcutoff = cutoff
		Glowpassthr = lowpassthr
		Gpclevelthr = pclevelthr
		
		startclip = core.std.ShufflePlanes(startclip, planes=0, colorfamily=vs.GRAY)	
		
		if((mode == "lowpass") or (mode == "lowpasspc")):
			lowpass = core.fmtc.resample(startclip, startclip.width*2, startclip.height*2, kernel=lowpasskernel, taps=lowpassintaps).fmtc.resample(startclip.width, startclip.height, kernel=lowpasskernel, taps=lowpassouttaps)
			
			if exportlowpass:
				return core.std.MakeDiff(startclip, lowpass, 0).std.Lut(function=MonoS.Luma16)
			
			difflow = core.std.MakeDiff(startclip, lowpass,0).rgvs.RemoveGrain([1] ).std.Lut(function=MonoS.LowPassLUT16)
			
			startclip = core.std.MergeDiff(startclip, difflow, 0)
			
		if((mode == "pclevel") or (mode == "lowpasspc")):
			diff = core.std.Lut(startclip, function=MonoS.PCLevelLUT16)
		else:
			temp1 = core.fmtc.resample(startclip, final_width, final_height, kernel=kernel, invks=True, invkstaps=invkstaps, taps=taps).fmtc.resample(clip.width, clip.height, kernel=kernel, taps=taps)
			diff = core.std.MakeDiff(startclip, temp1, 0)
		
		initial_mask = core.std.Lut(diff, function=MonoS.Luma16).rgvs.RemoveGrain(mode=[RGmode]).std.Lut(function=MonoS.f16)
		
		expanded = initial_mask
		for i in range(0, expandN):
			expanded = core.generic.Maximum(expanded, planes=[0])
		
		inflated = expanded
		for i in range(0, inflateN):
			inflated = core.generic.Inflate(inflated, planes=[0])
		
		final = core.fmtc.resample(inflated, final_width, final_height, src_left, src_top, src_width, src_height, taps=taps)
		
		if(blur_more):
			final = core.rgvs.RemoveGrain(final, mode=[12,0,0])
			
		final = core.std.ShufflePlanes(final, planes=0, colorfamily=vs.GRAY)
		
		if (clip.format.bits_per_sample == 8):
			final = core.fmtc.bitdepth(final, bits=8, mode=1)
		
		return final