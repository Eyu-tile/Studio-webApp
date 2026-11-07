# Tests

End-to-end tests for the `vs` tools on synthetic media made with ffmpeg (no network, ~30 s).

    python3 -m unittest discover -s tests -v

Needs ffmpeg (with libass, zscale, libvidstab for full coverage) and numpy.
