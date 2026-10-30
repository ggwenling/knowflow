# Original synthetic PDF fixtures — CC0-1.0

These files and their original generator are synthetic KnowFlow parser fixtures,
not user documents. The original fixture content is contributed under CC0 1.0:
https://creativecommons.org/publicdomain/zero/1.0/legalcode
Third-party libraries retain their own licenses.

chinese-pages.pdf has Chinese text on physical pages 1 and 3 and a blank page 2.
blank.pdf has no text; image-only.pdf contains a raster image with no text layer.
encrypted.pdf uses the public fixture-only password synthetic-test-password.
malformed.pdf deliberately has an invalid cross-reference/trailer.

The manifest pins committed bytes. ReportLab invariant fixtures reproduce bytes;
pypdf encryption uses randomness, so regenerated encrypted bytes may differ.
