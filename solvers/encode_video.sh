cd /home/shanthoshkv/foamstudio/nozzles/raptor3-frames
nice -n 19 ffmpeg -y -loglevel error -framerate 30 -i frame_%05d.png -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -movflags +faststart ../raptor3_plume_4k.mp4
nice -n 19 ffmpeg -y -loglevel error -framerate 30 -i frame_%05d.png -vf scale=1920:1080:flags=lanczos -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart ../raptor3_plume_1080p.mp4
ls -la ../raptor3_plume_*.mp4
