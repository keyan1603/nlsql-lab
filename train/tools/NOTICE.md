# Vendored llama.cpp converter

`convert_hf_to_gguf.py`, `conversion/` and `gguf-py/` come from the llama.cpp project (ggml-org/llama.cpp), which is released under the MIT licence.
They are used only by `train/merge_and_convert.py` to turn the merged Hugging Face model into a GGUF file for LM Studio.
The exact upstream revision was not recorded when the files were copied; to refresh them, copy the same paths from a current llama.cpp checkout.
