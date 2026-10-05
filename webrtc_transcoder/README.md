# PhantomEye WebRTC Transcoder (H.265 to H.264)

This directory contains a pre-configured `docker-compose.yml` that launches **MediaMTX with FFmpeg**. 

It is designed to solve the issue where IP Cameras stream in **H.265 (HEVC)**, which is natively unsupported by WebRTC in Chrome/Edge/Firefox. 

### What it does:
1. It listens on port `8889` for WebRTC (WHEP) requests.
2. When your dashboard requests a stream (e.g., `CAM-003`), it dynamically triggers FFmpeg.
3. FFmpeg pulls the heavy H.265 RTSP stream from your main camera IP.
4. It transcodes the video to **H.264 (libx264)** on-the-fly with zero latency.
5. It serves the highly compatible H.264 feed directly to your web browser via WebRTC!

### How to Deploy
You should run this on a server or computer that has good CPU/network (since transcoding requires CPU). 

1. Ensure Docker and Docker Compose are installed.
2. Open a terminal in this directory.
3. Run:
   ```bash
   docker-compose up -d
   ```

### Connecting the Dashboard
Once it is running, update your `frontend/js/live_stream.js` to point the `webrtcEndpoint` to wherever you deployed this Docker container. If you deployed it on `103.250.160.189`, the URL would be:
`http://103.250.160.189:8889/CAM-003/whep`
