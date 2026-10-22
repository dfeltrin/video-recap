"""Verifiche dell'ingestione senza eseguire inferenza sui modelli."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import converti_video as pipeline


class IngestioneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.input = self.base / 'input'
        self.output = self.base / 'output'
        self.input.mkdir()

    def esegui(self, *opzioni, errore_asr=False, codec='aac'):
        def worker(cmd):
            if errore_asr:
                raise subprocess.CalledProcessError(1, cmd)
            Path(cmd[3]).write_text('# Sintesi' if cmd[1].endswith('sintetizza_testo.py') else 'Trascrizione')
        log = io.StringIO()
        argv = ['converti_video.py', str(self.input), '--output', str(self.output), *opzioni]
        with patch.object(sys, 'argv', argv), patch('modelli_locali.verifica'), \
             patch.object(pipeline, 'importa_media_dropbox'), \
             patch.object(pipeline, 'codec_audio', return_value=codec), \
             patch.object(pipeline, 'durata_video', return_value=1), \
             patch.object(pipeline, 'esegui_trascrizione', side_effect=worker), \
             patch.object(pipeline, 'shutil') as shutil_mock, \
             contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            # Copia reale, altri controlli non dipendenti dai binari di sistema.
            import shutil
            shutil_mock.which.return_value = 'ffmpeg'
            shutil_mock.copy2.side_effect = shutil.copy2
            return pipeline.esegui(), log.getvalue()

    def test_m4a_copiato_trascritto_sintetizzato_e_rinominato(self):
        originale = self.input / 'Riunione.M4A'
        originale.write_bytes(b'audio originale')
        codice, _ = self.esegui('--lingua', 'Italian')
        self.assertEqual(codice, 0)
        self.assertEqual((self.output / 'Riunione.m4a').read_bytes(), b'audio originale')
        self.assertEqual((self.output / 'Riunione.txt').read_text(), 'Trascrizione')
        self.assertTrue((self.output / 'Riunione.sintesi.md').is_file())
        self.assertTrue((self.input / '_Riunione.M4A').is_file())
        self.assertFalse(originale.exists())
        self.assertFalse(list(self.output.glob('*.mp4')))
        codice, log = self.esegui()
        self.assertEqual(codice, 0)
        self.assertIn('Nessun file MOV o M4A', log)

    def test_download_rispetta_modalita_richiesta(self):
        from modelli_locali import MODELLO_ASR, MODELLO_SINTESI
        for opzioni, modelli in [([], [MODELLO_ASR, MODELLO_SINTESI]),
                                 (['--senza-sintesi'], [MODELLO_ASR]),
                                 (['--solo-sintesi'], [MODELLO_SINTESI]),
                                 (['--senza-testo'], None),
                                 (['--anteprima'], None)]:
            argv = ['converti_video.py', str(self.input), '--output', str(self.output),
                    '--scarica-modelli', *opzioni]
            self.output.mkdir(exist_ok=True)
            with self.subTest(opzioni=opzioni), patch.object(sys, 'argv', argv), \
                 patch('modelli_locali.verifica') as verifica, \
                 patch.object(pipeline, 'importa_media_dropbox'), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pipeline.esegui(), 0)
                if modelli is None:
                    verifica.assert_not_called()
                else:
                    verifica.assert_called_once_with(modelli, scarica=True)

    def test_senza_testo_copia_solo_audio(self):
        (self.input / 'nota.m4a').write_bytes(b'audio')
        codice, _ = self.esegui('--senza-testo')
        self.assertEqual(codice, 0)
        self.assertEqual({p.name for p in self.output.iterdir()}, {'nota.m4a'})

    def test_senza_sintesi(self):
        (self.input / 'nota.m4a').write_bytes(b'audio')
        codice, _ = self.esegui('--senza-sintesi')
        self.assertEqual(codice, 0)
        self.assertEqual({p.name for p in self.output.iterdir()}, {'nota.m4a', 'nota.txt'})

    def test_anteprima_non_modifica_file(self):
        (self.input / 'nota.m4a').write_bytes(b'audio')
        codice, log = self.esegui('--anteprima')
        self.assertEqual(codice, 0)
        self.assertIn('cp -p', log)
        self.assertIn('trascrivi_audio.py', log)
        self.assertIn('sintetizza_testo.py', log)
        self.assertNotIn('.mp4', log)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.input / 'nota.m4a').exists())

    def test_errore_conserva_originale_e_consente_ripresa(self):
        (self.input / 'nota.m4a').write_bytes(b'audio')
        codice, _ = self.esegui(errore_asr=True)
        self.assertEqual(codice, 1)
        self.assertTrue((self.input / 'nota.m4a').exists())
        self.assertFalse((self.output / 'nota.txt').exists())
        self.assertEqual((self.output / 'nota.m4a').read_bytes(), b'audio')
        (self.output / 'nota.m4a').write_bytes(b'copia gia presente')
        codice, _ = self.esegui()
        self.assertEqual(codice, 0)
        self.assertEqual((self.output / 'nota.m4a').read_bytes(), b'copia gia presente')
        self.assertTrue((self.input / '_nota.m4a').exists())

    def test_audio_senza_traccia_non_viene_segnato_completato(self):
        (self.input / 'nota.m4a').write_bytes(b'audio')
        codice, _ = self.esegui(codec='')
        self.assertEqual(codice, 1)
        self.assertTrue((self.input / 'nota.m4a').exists())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_collisione_con_mov_attivo_o_completato(self):
        (self.input / 'nota.m4a').write_bytes(b'audio')
        for nome in ['NOTA.MOV', '_NOTA.MOV']:
            with self.subTest(nome=nome):
                video = self.input / nome
                video.write_bytes(b'video')
                with self.assertRaises(SystemExit) as errore:
                    self.esegui()
                self.assertEqual(errore.exception.code, 2)
                self.assertFalse(self.output.exists())
                video.unlink()

    def test_anteprima_mov_continua_a_prevedere_mp4(self):
        (self.input / 'filmato.mov').write_bytes(b'video')
        codice, log = self.esegui('--anteprima')
        self.assertEqual(codice, 0)
        for estensione in ['.mp4', '.m4a', '.txt', '.sintesi.md']:
            self.assertIn('filmato' + estensione, log)

    def test_importazione_dropbox_m4a_anteprima_duplicati_e_trasferimento(self):
        home = self.base / 'home'
        dropbox = home / 'Dropbox' / 'Screenshot'
        dropbox.mkdir(parents=True)
        (dropbox / 'Nuova.M4A').write_bytes(b'nuova')
        (dropbox / 'Gia.m4a').write_bytes(b'duplicato')
        (dropbox / 'altra.wav').write_bytes(b'ignora')
        (self.input / '_GIA.M4A').write_bytes(b'originale')
        with patch.object(pipeline.Path, 'home', return_value=home), contextlib.redirect_stdout(io.StringIO()):
            pipeline.importa_media_dropbox(self.input, anteprima=True)
            self.assertFalse((self.input / 'Nuova.M4A').exists())
            self.assertTrue((dropbox / 'Nuova.M4A').exists())
            pipeline.importa_media_dropbox(self.input)
        self.assertEqual((self.input / 'Nuova.M4A').read_bytes(), b'nuova')
        self.assertFalse((dropbox / 'Nuova.M4A').exists())
        self.assertTrue((dropbox / 'Gia.m4a').exists())
        self.assertTrue((dropbox / 'altra.wav').exists())


if __name__ == '__main__':
    unittest.main()
