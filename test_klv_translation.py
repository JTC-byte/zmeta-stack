from klv_sample_input import klv_sample
from klv_to_zmeta import klv_to_zmeta
from pprint import pprint

# Translate and print
zmeta_output = klv_to_zmeta(klv_sample)
print("✅ ZMeta Output:")
pprint(zmeta_output)
