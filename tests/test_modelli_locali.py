"""Verifiche offline del caricamento e dei limiti di generazione, senza GPU."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelli_locali as locali
import sintetizza_testo as sintesi


class ModelliLocaliTest(unittest.TestCase):
    def test_tokenizer_bpe_asr_senza_tokenizer_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'config.json').write_text('{}')
            (base / 'model.safetensors').write_bytes(b'pesi')
            (base / 'vocab.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'tokenizer mancante'):
                locali.percorso_modello(tmp)
            (base / 'merges.txt').write_text('#version: 0.2\n')
            self.assertEqual(locali.percorso_modello(tmp), base.resolve())
            (base / 'vocab.json').unlink()
            with self.assertRaisesRegex(RuntimeError, 'tokenizer mancante'):
                locali.percorso_modello(tmp)

    def test_cartella_locale_e_shard_mancante(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'config.json').write_text('{}')
            (base / 'tokenizer.json').write_text('{}')
            (base / 'model-1.safetensors').write_bytes(b'pesi')
            self.assertEqual(locali.percorso_modello(tmp), base.resolve())
            (base / 'model.safetensors.index.json').write_text(json.dumps({
                'weight_map': {'a': 'model-1.safetensors', 'b': 'model-2.safetensors'}}))
            with self.assertRaisesRegex(RuntimeError, 'incompleto'):
                locali.percorso_modello(tmp)

    def test_esecuzione_cerca_soltanto_nella_cache(self):
        downloader = Mock(side_effect=OSError('non presente'))
        with patch.dict(sys.modules, {'huggingface_hub': SimpleNamespace(snapshot_download=downloader)}):
            with self.assertRaisesRegex(RuntimeError, 'setup_sintesi.sh'):
                locali.percorso_modello('organizzazione/modello')
            self.assertTrue(downloader.call_args.kwargs['local_files_only'])
            with self.assertRaises(RuntimeError):
                locali.percorso_modello('organizzazione/modello', scarica=True)
            self.assertFalse(downloader.call_args.kwargs['local_files_only'])

    def test_verifica_scarica_solo_modelli_mancanti_o_incompleti(self):
        for errore in [None, RuntimeError('non disponibile'), RuntimeError('incompleto')]:
            with self.subTest(errore=errore), \
                 patch.object(locali.platform, 'system', return_value='Darwin'), \
                 patch.object(locali.platform, 'machine', return_value='arm64'), \
                 patch.object(locali.importlib.util, 'find_spec', return_value=object()), \
                 patch.object(locali, 'percorso_modello') as percorso, \
                 contextlib.redirect_stdout(io.StringIO()):
                percorso.side_effect = [errore, Path('/cache/modello')] if errore else [Path('/cache/modello')]
                locali.verifica([locali.MODELLO_ASR, locali.MODELLO_ASR], scarica=True)
                attese = [call(locali.MODELLO_ASR)]
                if errore:
                    attese.append(call(locali.MODELLO_ASR, scarica=True))
                self.assertEqual(percorso.call_args_list, attese)

    def test_download_fallito_o_cartella_incompleta_bloccano_avvio(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(locali.platform, 'system', return_value='Darwin'), \
             patch.object(locali.platform, 'machine', return_value='arm64'), \
             patch.object(locali.importlib.util, 'find_spec', return_value=object()), \
             patch.object(locali, 'percorso_modello', side_effect=RuntimeError('incompleto')) as percorso, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                locali.verifica([tmp], scarica=True)
            percorso.assert_called_once_with(tmp)
            percorso.reset_mock()
            with self.assertRaises(RuntimeError):
                locali.verifica([locali.MODELLO_ASR], scarica=True)
            self.assertEqual(percorso.call_count, 2)

    def test_risposta_troncata_o_thinking_non_pubblicata(self):
        sessione = locali.SintesiLocale.__new__(locali.SintesiLocale)
        sessione.model = object()
        sessione.tokenizer = Mock()
        sessione.tokenizer.apply_chat_template.return_value = [1, 2]
        for testo, motivo, valido in [('Report', 'stop', True), ('Parziale', 'length', False),
                                       ('<think>interno</think>', 'stop', False), ('', 'stop', False)]:
            with self.subTest(testo=testo, motivo=motivo):
                evento = SimpleNamespace(text=testo, finish_reason=motivo, generation_tokens=3)
                stream = Mock(return_value=iter([evento]))
                with patch.dict(sys.modules, {
                    'mlx': SimpleNamespace(core=SimpleNamespace(random=SimpleNamespace(seed=Mock()))),
                    'mlx.core': SimpleNamespace(random=SimpleNamespace(seed=Mock())),
                    'mlx_lm': SimpleNamespace(stream_generate=stream),
                    'mlx_lm.sample_utils': SimpleNamespace(make_sampler=Mock()),
                }), contextlib.redirect_stdout(io.StringIO()):
                    if valido:
                        self.assertEqual(sessione.genera([], 'Test'), testo)
                    else:
                        with self.assertRaises(RuntimeError):
                            sessione.genera([], 'Test')
                    with self.assertRaisesRegex(ValueError, 'contesto'):
                        sessione.genera([], 'Test', max_output=10, contesto=11)
                self.assertFalse(sessione.tokenizer.apply_chat_template.call_args.kwargs['enable_thinking'])

    def test_divisione_preserva_caratteri_e_limite(self):
        tokenizer = SimpleNamespace(encode=lambda testo, **kwargs: list(testo))
        testo = 'Prima parte.\n\n Seconda parte, con accenti: è così.  '
        parti = sintesi.dividi_testo(testo, tokenizer, 18)
        self.assertEqual(''.join(parti), testo)
        self.assertTrue(all(len(p) <= 18 for p in parti))
        with self.assertRaises(ValueError):
            sintesi.dividi_testo('parolalunghissima', tokenizer, 3)


if __name__ == '__main__':
    unittest.main()
