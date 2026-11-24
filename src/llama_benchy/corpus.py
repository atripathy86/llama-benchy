import os
import hashlib
import re
import requests
from typing import Any, List, Optional, Tuple


_DEPLOYMENT_SUFFIX = re.compile(
    r"[-_.](?:"
    r"awq|gptq|gguf|exl2|exl3|mlx|fp8|fp16|bf16|int4|int8|"
    r"nvfp4|w4a16|w8a8|hqq|bnb|[234568]bit|q[2-8](?:_[kmq]\w*)*"
    r")$",
    re.IGNORECASE,
)


class LightweightTokenizer:
    def __init__(self, tokenizer: Any):
        self._tokenizer = tokenizer

    @classmethod
    def from_pretrained(
        cls, name: str, token: Optional[str] = None
    ) -> "LightweightTokenizer":
        from tokenizers import Tokenizer

        if os.path.isfile(name):
            tokenizer = Tokenizer.from_file(name)
        else:
            tokenizer_json = os.path.join(name, "tokenizer.json")
            if os.path.isdir(name) and os.path.exists(tokenizer_json):
                tokenizer = Tokenizer.from_file(tokenizer_json)
            else:
                tokenizer = Tokenizer.from_pretrained(name, token=token)
        return cls(tokenizer)

    def encode(self, text: str, add_special_tokens: bool = False):
        return self._tokenizer.encode(
            text, add_special_tokens=add_special_tokens
        ).ids

    def decode(self, token_ids):
        return self._tokenizer.decode(list(token_ids), skip_special_tokens=False)


class TokenizedCorpus:
    def __init__(self, book_url: str, tokenizer_name: Optional[str], model_name: str):
        self.book_url = book_url
        self.tokenizer = self._get_tokenizer(model_name, tokenizer_name)
        self.tokens = self._load_data()

    def _get_transformers_tokenizer(self, name: str):
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(
            name,
            use_fast=True,
            trust_remote_code=False,
            token=self._hf_token(),
        )

    @staticmethod
    def _hf_token() -> Optional[str]:
        return os.environ.get("HF_TOKEN") or os.environ.get(
            "HUGGING_FACE_HUB_TOKEN"
        )

    def _try_tokenizer(self, name: str) -> Tuple[Optional[Any], List[str]]:
        errors: List[str] = []
        try:
            return LightweightTokenizer.from_pretrained(name, self._hf_token()), errors
        except Exception as e:
            errors.append(f"lightweight tokenizer error: {e}")

        try:
            return self._get_transformers_tokenizer(name), errors
        except Exception as e:
            errors.append(f"transformers tokenizer error: {e}")
            return None, errors

    @staticmethod
    def _tokenizer_stem(name: str) -> Optional[str]:
        if os.path.exists(name):
            return None

        prefix, separator, leaf = name.rpartition("/")
        stem = leaf
        while True:
            stripped = _DEPLOYMENT_SUFFIX.sub("", stem)
            if stripped == stem:
                break
            stem = stripped
        if stem == leaf:
            return name if not separator else None
        return f"{prefix}/{stem}" if separator else stem

    @staticmethod
    def _resolve_hf_tokenizer(name: str) -> Optional[str]:
        stem = TokenizedCorpus._tokenizer_stem(name)
        if not stem:
            return None

        from huggingface_hub import HfApi

        token = TokenizedCorpus._hf_token()
        api = HfApi()
        _, separator, leaf = stem.rpartition("/")
        try:
            if separator:
                model_ids = [api.model_info(stem, token=token).id]
            else:
                model_ids = [
                    model.id
                    for model in api.list_models(
                        search=leaf,
                        limit=50,
                        token=token,
                    )
                    if model.id.rsplit("/", 1)[-1].lower() == leaf.lower()
                ]
                model_ids = list(dict.fromkeys(model_ids))
        except Exception as e:
            print(f"Could not search Hugging Face for tokenizer '{stem}': {e}")
            return None

        if len(model_ids) == 1:
            return model_ids[0]
        if len(model_ids) > 1:
            print(
                f"Found multiple Hugging Face models for tokenizer stem '{leaf}'; "
                "not choosing one automatically."
            )
        return None

    def _get_tokenizer(self, model_name: str, tokenizer_name: Optional[str] = None):
        requested_name = tokenizer_name if tokenizer_name else model_name
        tokenizer, errors = self._try_tokenizer(requested_name)
        if tokenizer is not None:
            return tokenizer

        resolved_name = None
        if tokenizer_name is None:
            resolved_name = self._resolve_hf_tokenizer(model_name)
            if resolved_name and resolved_name != requested_name:
                print(
                    f"Tokenizer '{requested_name}' was not available; "
                    f"resolved Hugging Face tokenizer to '{resolved_name}'."
                )
                tokenizer, resolved_errors = self._try_tokenizer(resolved_name)
                errors.extend(resolved_errors)
                if tokenizer is not None:
                    return tokenizer

        attempted_names = (
            f"'{requested_name}' and '{resolved_name}'"
            if resolved_name
            else f"'{requested_name}'"
        )
        print(
            f"Error loading tokenizer {attempted_names}: "
            + "; ".join(errors)
        )
        print("Falling back to 'gpt2' tokenizer as approximation.")
        try:
            return LightweightTokenizer.from_pretrained("gpt2", self._hf_token())
        except Exception:
            return self._get_transformers_tokenizer("gpt2")

    def _load_data(self):
        try:
            # Create cache directory if it doesn't exist
            cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "llama-benchy")
            os.makedirs(cache_dir, exist_ok=True)
            
            # Generate hash of the URL for the filename
            url_hash = hashlib.md5(self.book_url.encode()).hexdigest()
            cache_file = os.path.join(cache_dir, f"{url_hash}.txt")
            
            if os.path.exists(cache_file):
                print(f"Loading text from cache: {cache_file}")
                with open(cache_file, "r", encoding="utf-8") as f:
                    text = f.read()
            else:
                print(f"Downloading book from {self.book_url}...")
                response = requests.get(self.book_url)
                response.raise_for_status()
                text = response.text
                # Basic cleanup
                start_idx = text.find("*** START OF THE PROJECT GUTENBERG EBOOK")
                if start_idx != -1:
                    text = text[start_idx:]
                
                # Save to cache
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"Saved text to cache: {cache_file}")
                
            return self.tokenizer.encode(text, add_special_tokens=False)
        except Exception as e:
            print(f"Error downloading or processing book: {e}")
            exit(1)

    def get_tokenizer(self):
        return self.tokenizer

    def get_tokens(self):
        return self.tokens

    def __len__(self):
        return len(self.tokens)
