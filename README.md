This script uses python api for RenderDoc to find a first draw call which, 
when called several times with the same input, gives a different output.
This indicates an issue in the application or in the driver. The script was
made to help with the investigations of bugs in Mesa 3D graphics library.

The script requires renderdoc python module (`renderdoc.pyd` or 
`renderdoc.so` depending on your platform) and main renderdoc library
(`renderdoc.dll` or `librenderdoc.so`).


Usage example:

```
LD_LIBRARY_PATH=/path/to/renderdoc/lib python3 flaky_finder.py \
 --python-module=/path/to/renderdoc/py/module --rdc=capture.rdc
```

```
Transferring capture: |████████████████████████████████████████████████████████████████████████| 100.0% 
Draw Calls: |█████████████████████████████████████████████████████████████████---------| 91.7% Checked
Found discrepancy in EID 5992, resource <ResourceId 1243644>
```

It's possible to specify remote server with `--host`.

See https://renderdoc.org/docs/python_api/examples/renderdoc_intro.html for
more information about python api for RenderDoc.
