# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 1.1 - 2026-09-26

Output for SignMaster and other cutter software, a real-world output size, and fixes for the most common failed jobs. Nothing has moved on the screen.

### Added

- **PDF output.** A single-page vector PDF whose page size is the physical size of the design. SignMaster V5 imports PDF through its dedicated PDF importer.
- **PLT (HPGL) output.** The native language of plotters and vinyl cutters. The file holds cut paths only, with no fill and no background. Curves are written as short straight segments within 0.05 mm, and holes are cut before their outer contour so the material does not shift.
- **DPI setting.** New field "Rozdzielczość (DPI)" in the "Format pliku wyjściowego" card, default 96. It gives every format the same physical size: size in mm = pixels ÷ DPI × 25.4. DPI only scales the result and never changes the traced shape.
- **Output size readout.** As soon as an image is loaded, the line under the DPI field shows the final size, for example "Rozmiar wyniku: 101,6 × 67,7 mm".
- **DPI from the image.** When the image file stores its resolution, the DPI field fills in by itself and the size line says "DPI odczytane z pliku". A value you typed is kept for images without a stored resolution.
- **Background hint.** After an image is loaded, a hint under the preview warns when the background would be traced as a frame, for example for a dark logo on a light background. One click sets "Odwróć" the right way. The check runs again when the colour channel or threshold mode changes.
- **Frame warning.** While a background colour is set, a line under the colours explains that SVG, EPS and PDF will contain a rectangle, which cutting software cuts as a frame.
- **Preview for every conversion.** The preview now appears even when SVG is not among the chosen formats. The SVG is then used only for the preview and is not offered for saving.
- **Paste from the clipboard.** Ctrl+V loads an image copied from another program.
- **Help texts.** New DPI help with worked examples, including how to reach a specific width. The "Formaty" help now also describes PDF and PLT.
- **Command line.** New `--dpi` flag, and `--formats` accepts `pdf` and `plt`. The summary line shows the physical size.
- EPS files now include a `%%HiResBoundingBox` line.

### Changed

- **EPS size now follows DPI.** Version 1.0 wrote EPS at an implicit 72 DPI while SVG used 96, so one conversion came out at two different sizes. At the default 96 DPI, EPS files are now 25 % smaller than in 1.0 and match the SVG. Set DPI to 72 to get exactly the 1.0 EPS output.
- **SVG width and height are given in millimetres.** Path data is unchanged, and at the default 96 DPI the SVG appears at the same size as in 1.0.
- **Presets keep your output choices.** Clicking a preset no longer resets the format checkboxes, and it leaves DPI as you set it.
- The full-size preview fits the SVG to the window at any DPI.
- New dependency: Pillow, used to read the resolution stored in image files. `run.bat` installs it automatically.

### Fixed

- **Transparent images.** Transparent PNG, WEBP and TIFF images no longer come out empty or as a solid rectangle. Transparent areas are placed on a background that contrasts with the visible content, so the image behaves like the same design on a white or black background.
- **Works offline.** Styling, icons and scripts now ship with the app, so the page works without an internet connection.
- **"Szablon" preset.** Shapes inside a hole are no longer turned into holes. The stencil comes out as one solid shape.
- **Polish letters in paths.** Images whose file name or folder contains letters such as "ł" or "ż" now load, on the command line as well.
- **Polygon output.** SVG files in polygon mode now contain real straight lines instead of curves, which makes them about a third of the size. Converting to SVG is about twice as fast in every mode.
- **Clear error messages.** Invalid settings are reported in Polish with the field name, for example "Pole „Skalowanie w górę”: dozwolony zakres to 1–4.", instead of technical errors. An unsupported colour name no longer leaves a half-written result. Files that are too large and failed saves also get a Polish message.
- **Unsupported files.** The file picker shows only supported formats. Other files, whether dropped or pasted, are rejected with a clear message.
- **File names.** A custom file name can no longer contain folders or characters that Windows does not allow; they are replaced with "_".

### Documentation

- README: new output formats section, the `dpi` parameter, a workflow step for formats and DPI, notes on the new helpers, a new CLI example, the Pillow dependency, a link to this changelog and a complete project structure.
- Fixed two README examples that did not work in 1.0. The CLI preset example used `ploter`, which exists in the web UI only. The config example used `"background": null`, which is ignored; `"none"` gives a transparent background.

### Known issues

- The "Ploter / Cutter" preset is available in the web UI only, not on the command line.

## 1.0 - 2026-05-23

Initial release.

- Browser UI to upload an image, adjust settings, preview the result and save it, plus a command-line mode.
- SVG and EPS output.
- 9 presets: Ploter / Cutter, Logo, Ikona, Sylwetka, Szkic, Wysoka jakość, Kompaktowy, Szablon, Ciemne na jasnym.
- Every conversion setting available in the UI, with help popovers in Polish.
- Staging folder with explicit saving, a native folder picker and automatic cleanup.
- `run.bat` launcher that updates the project, prepares Python and starts the app.
