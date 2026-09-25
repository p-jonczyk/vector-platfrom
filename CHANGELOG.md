# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 1.1 - 2026-09-26

Output for SignMaster and other cutter software, and a real-world output size.

### Added

- **PDF output.** A single-page vector PDF whose page size is the physical size of the design. SignMaster V5 imports PDF through its dedicated PDF importer.
- **PLT (HPGL) output.** The native language of plotters and vinyl cutters. The file holds cut paths only, with no fill and no background. Curves are written as short straight segments within 0.05 mm, and holes are cut before their outer contour so the material does not shift.
- **DPI setting.** New field "Rozdzielczość (DPI)" in the "Format pliku wyjściowego" card, default 96. It gives every format the same physical size: size in mm = pixels ÷ DPI × 25.4. DPI only scales the result and never changes the traced shape.
- **Output size readout.** As soon as an image is loaded, the line under the DPI field shows the final size, for example "Rozmiar wyniku: 101,6 × 67,7 mm".
- **Help texts.** New DPI help with worked examples, including how to reach a specific width. The "Formaty" help now also describes PDF and PLT.
- **Command line.** New `--dpi` flag, and `--formats` accepts `pdf` and `plt`. The summary line shows the physical size.
- EPS files now include a `%%HiResBoundingBox` line.

### Changed

- **EPS size now follows DPI.** Version 1.0 wrote EPS at an implicit 72 DPI while SVG used 96, so one conversion came out at two different sizes. At the default 96 DPI, EPS files are now 25 % smaller than in 1.0 and match the SVG. Set DPI to 72 to get exactly the 1.0 EPS output.
- **SVG width and height are given in millimetres.** Path data is unchanged, and at the default 96 DPI the SVG appears at the same size as in 1.0.
- **Presets keep your output choices.** Clicking a preset no longer resets the format checkboxes, and it leaves DPI as you set it.
- The note shown when there is no preview now reads "Podgląd dostępny tylko przy zaznaczonym SVG" instead of mentioning EPS only.
- The full-size preview fits the SVG to the window at any DPI.

### Documentation

- README: new output formats section, the `dpi` parameter, a workflow step for formats and DPI, a new CLI example, a link to this changelog and a complete project structure.
- Fixed two README examples that did not work in 1.0. The CLI preset example used `ploter`, which exists in the web UI only. The config example used `"background": null`, which is ignored; `"none"` gives a transparent background.

### Known issues

- Dark shapes on a light background also trace the background, which adds a frame around the design. Workaround: tick "Odwróć (ciemne na jasnym tle)" or use the "Ciemne na jasnym" preset.
- Transparent PNG images come out empty or as a solid rectangle. Workaround: place the image on a white background before uploading.
- A background colour is written into SVG, EPS and PDF as a filled rectangle, which cutting software cuts as a frame. Workaround: click "Przezroczyste tło". PLT files are not affected.
- The "Szablon" preset turns shapes that sit inside a hole into holes.
- The web UI needs an internet connection to load its styling and scripts.
- The "Ploter / Cutter" preset is available in the web UI only, not on the command line.

## 1.0 - 2026-05-23

Initial release.

- Browser UI to upload an image, adjust settings, preview the result and save it, plus a command-line mode.
- SVG and EPS output.
- 9 presets: Ploter / Cutter, Logo, Ikona, Sylwetka, Szkic, Wysoka jakość, Kompaktowy, Szablon, Ciemne na jasnym.
- Every conversion setting available in the UI, with help popovers in Polish.
- Staging folder with explicit saving, a native folder picker and automatic cleanup.
- `run.bat` launcher that updates the project, prepares Python and starts the app.
