# scripts

This repository contains a collection of shell scripts that I use regularly on my Linux systems. They help with screen recording, screenshots, power management, and other everyday tasks.

## Features

- `record`: Screen recording via `ffmpeg`, `dmenu`, and `notify-send`. Supports full screen, area, and active window.
- `screenshot`: Flexible screenshot tool with dmenu-based interface (full screen, area, window, color picker).
- `powermenu`: Simple power menu with shutdown, reboot, lock, and more.
- `newlook`: Change the colors and wallpaper with `pywal`.

## Requirements

These scripts rely on commonly available tools:

- `ffmpeg`
- `import`
- `slop`
- `xdotool`
- `xwininfo`
- `xdpyinfo`
- `dmenu`
- `dunst`
- `notify-send`
- `pywal`
- `wpctl`
- `amixer`
- `sigdwmblocks`

Make sure these are installed on your system.

## Usage

Each script is self-contained and can be executed directly. Some scripts offer an interactive menu if no arguments are provided.

```bash
./record            # interactive dmenu to start recording
./record screen     # record full screen
./record stop       # stop current recording
```

## Customization

You can edit variables such as:

- `AUDIO_SRC` (default PulseAudio source)
- `PRESET` (for ffmpeg encoding speed)
- `FRAMERATE`
- Color schemes in `dmenu` prompts

## Disclaimer

I'm not a professional developer - just a hobbyist sharing my personal setup.  
This build is provided as-is, with no guarantees that it will work for you.  
If something breaks, you're on your own - but feel free to explore, adapt, and improve!
