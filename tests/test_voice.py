"""Офлайн-тести ukr-voice: розмітка, запити до Gemini, сценарії, пресети. Мережа й моделі не потрібні."""
import json
import os
import tempfile
import unittest
import wave

from _paths import add_script_path

add_script_path('ukr-voice')
import gemini_tts as G  # noqa: E402
import markup as M  # noqa: E402
import ukr_voice as V  # noqa: E402


class MarkupTest(unittest.TestCase):
    def test_emotions_split_parts(self):
        parts = M.to_gemini('(обурено) Не собак! / (радісно) *Котів*!')
        self.assertEqual(len(parts), 2)
        self.assertIn('indignant', parts[0][1][0])
        self.assertIn('[short pause]', parts[0][0])
        self.assertEqual(parts[1][0], 'Котів!')
        self.assertTrue(any('«Котів»' in s for s in parts[1][1]))

    def test_pauses_and_stress(self):
        (text, _), = M.to_gemini('Замок /// за+мок [0.2] кінець')
        self.assertIn('[long pause]', text)
        self.assertIn('за́мок', text)
        self.assertIn('[pause]', text)

    def test_unknown_parentheses_stay(self):
        (text, style), = M.to_gemini('Деталі (див. нижче) тут')
        self.assertEqual(text, 'Деталі (див. нижче) тут')
        self.assertEqual(style, [])

    def test_spans(self):
        parts = M.to_gemini('Звичайно {тихо повільно: таємниця} кінець')
        self.assertEqual([p[0] for p in parts], ['Звичайно', 'таємниця', 'кінець'])
        self.assertEqual(parts[1][1], ['quietly', 'slower pace'])

    def test_plain(self):
        self.assertEqual(M.plain('(радісно) Ого~! / *Дуже* за+мок {швидко: так}'), 'Ого! Дуже замок так')

    def test_lexicon(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'lex.json')
        json.dump({'Ніко': 'Ніко+'}, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
        self.assertEqual(M.apply_lexicon('Привіт, Ніко! Ніко+ вже тут.', p), 'Привіт, Ніко+! Ніко+ вже тут.')

    def test_split_sentences(self):
        text = 'Речення номер один. ' * 50
        chunks = M.split_sentences(text.strip(), 200)
        self.assertTrue(all(len(c) <= 200 for c in chunks))
        self.assertEqual(' '.join(chunks), text.strip())


class GeminiBodyTest(unittest.TestCase):
    def test_single_voice_modern(self):
        b = G.build_body([{'text': 'Привіт', 'style': ['joyful']}], 'Kore', 'gemini-3.8-flash-tts', 'warm')
        part = b['contents'][0]['parts'][0]
        self.assertEqual(part['text'], 'Привіт')
        self.assertEqual(part['speechMetadata']['style'], 'warm; joyful')
        self.assertEqual(b['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'], 'Kore')

    def test_multi_speaker(self):
        b = G.build_body([{'text': 'А', 'speaker': 'Оля'}, {'text': 'Б', 'speaker': 'Тарас'}],
                         {'Оля': 'Zephyr', 'Тарас': 'Charon'}, 'gemini-3.8-flash-tts')
        cfg = b['generationConfig']['speechConfig']['multiSpeakerVoiceConfig']['speakerVoiceConfigs']
        self.assertEqual([c['speaker'] for c in cfg], ['Оля', 'Тарас'])
        self.assertEqual(b['contents'][0]['parts'][1]['speechMetadata']['speaker'], 'Тарас')

    def test_legacy_model_style_prefix(self):
        b = G.build_body([{'text': 'Привіт', 'style': ['calm']}], 'Kore', 'gemini-2.5-flash-preview-tts')
        self.assertTrue(b['contents'][0]['parts'][0]['text'].startswith('Read in this manner (calm)'))

    def test_pcm_to_wav(self):
        wav = G.pcm_to_wav(b'\x00\x00' * 2400)
        p = os.path.join(tempfile.mkdtemp(), 'a.wav')
        open(p, 'wb').write(wav)
        with wave.open(p) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getnframes()), (24000, 1, 2400))

    def test_aliases(self):
        self.assertEqual(G.resolve_model('lite'), 'gemini-3.8-flash-lite-tts')


class CliHelpersTest(unittest.TestCase):
    def test_dialog_parse(self):
        p = os.path.join(tempfile.mkdtemp(), 's.txt')
        open(p, 'w', encoding='utf-8').write('# коментар\nОля: Привіт!\nТарас: Вітаю.\nпродовження репліки\n')
        self.assertEqual(V.parse_dialog(p), [('Оля', 'Привіт!'), ('Тарас', 'Вітаю. продовження репліки')])

    def test_auto_cast_gemini(self):
        cast = V.auto_cast(['Оля', 'Тарас', 'Микола', 'Ірина'], 'gemini')
        self.assertEqual(len(set(cast.values())), 4)
        female = {v['name'] for v in V.gemini_voices() if v['gender'] == 'f'}
        self.assertIn(cast['Оля'], female)
        self.assertNotIn(cast['Микола'], female)

    def test_presets_cover_both_engines(self):
        for name, p in json.load(open(os.path.join(V.SKILL, 'assets', 'presets.json'), encoding='utf-8')).items():
            self.assertIn('gemini', p, name)
            self.assertIn('holos', p, name)
            self.assertTrue(V.is_gemini_voice(p['gemini']['voice']), name)

    def test_concat_wavs(self):
        d = tempfile.mkdtemp()
        a, out = G.pcm_to_wav(b'\x01\x00' * 240), os.path.join(d, 'o.wav')
        V.concat_wavs([a, a], out, gap=0.01)
        with wave.open(out) as w:
            self.assertEqual(w.getnframes(), 240 * 2 + 240)


if __name__ == '__main__':
    unittest.main()
