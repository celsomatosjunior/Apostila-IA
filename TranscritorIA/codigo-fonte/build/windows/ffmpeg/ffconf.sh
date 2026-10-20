#!/bin/sh
# FFmpeg/FFprobe mínimos do Transcritor IA (LGPL 2.1+, sem GPL e sem "nonfree").
# Somente o necessário para LER o áudio de arquivos de áudio e vídeo:
# nenhum decodificador de vídeo é incluído — os quadros de imagem nunca são decodificados.
COMMON="--disable-everything --disable-autodetect --disable-network --disable-doc --disable-ffplay --disable-debug \
 --disable-gpl --disable-nonfree --disable-version3 --disable-avdevice --disable-postproc --disable-swscale \
 --enable-ffmpeg --enable-ffprobe \
 --enable-protocol=pipe,file \
 --enable-demuxer=mov,matroska,avi,asf,mpegps,mpegts,mpegvideo,flv,mp3,wav,ogg,flac,aac,ac3,eac3,amr,w64,aiff,caf,dts,truehd,m4v,h264,hevc \
 --enable-muxer=wav,null,pcm_s16le \
 --enable-decoder=aac,aac_latm,mp3,mp3float,mp2,mp2float,mp1,ac3,eac3,opus,vorbis,flac,alac,wmav1,wmav2,wmapro,wmavoice,amrnb,amrwb,dca,truehd,mlp,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,pcm_u8,pcm_alaw,pcm_mulaw,pcm_dvd,pcm_bluray,adpcm_ima_wav,adpcm_ms,gsm,gsm_ms,speex \
 --enable-encoder=pcm_s16le \
 --enable-parser=aac,aac_latm,mpegaudio,ac3,opus,vorbis,flac,dca,mlp \
 --enable-bsf=aac_adtstoasc \
 --enable-filter=aresample,aformat,anull,amix,pan"
