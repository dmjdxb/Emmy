# Third-Party Notices

Robin by EnergyIR incorporates open-source software. The principal components
and their licences are listed below. This file is referenced from the in-app
**Settings → About & Licences** screen and from `LICENSE`.

## Upstream base — Hermes Agent (MIT)

Robin is built on **Hermes Agent** by Nous Research, used under the MIT License.
Robin (the larger work) is proprietary to EnergyIR (see `LICENSE`), but the
Hermes Agent components remain under the MIT License, whose copyright and
permission notice is retained verbatim below as that license requires. Robin and
EnergyIR are independent of, and not endorsed by, Nous Research; "Hermes" and
"Nous Research" remain marks of Nous Research.

```
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Runtime / frameworks

| Component | Licence |
|---|---|
| Electron | MIT |
| Node.js | MIT-style (see Node.js licence) |
| React / React DOM | MIT |
| Vite | MIT |
| Python (CPython) | PSF License |

## Model provider

- **DeepSeek V4 Pro** is accessed through the **Together AI** API. The model and
  the inference service are operated by their respective owners under their own
  terms; they are not redistributed with Robin.

## Generating a full inventory

A complete, version-pinned dependency licence inventory is produced at build
time from `package-lock.json` / `uv.lock`. To regenerate locally:

```bash
npx license-checker --production --summary    # Node dependencies
pip-licenses                                   # Python dependencies
```

If you redistribute Robin, include this file and the retained MIT notice in
`LICENSE`, as those licences require.
