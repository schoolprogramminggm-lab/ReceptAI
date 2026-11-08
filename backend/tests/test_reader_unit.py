"""Быстрая проверка reader.py без вызова Gemini API."""
import sys
sys.path.insert(0, ".")

from ai.reader import _convert_to_jpeg, _validate_json, _load_prompt

# Тест 1: prompt загружается
prompt = _load_prompt()
assert len(prompt) > 100, "prompt слишком короткий"
print("OK: prompt.txt загружается")

# Тест 2: JSON-валидатор — правильный JSON
valid = _validate_json(
    '[{"name":"Атропин","form":"капли","dose":"1 кап",'
    '"frequency":"2 раза","duration":"7 дней","sure":true}]'
)
assert len(valid) == 1
assert valid[0]["name"] == "Атропин"
assert valid[0]["sure"] is True
print("OK: JSON-валидатор работает")

# Тест 3: мусорный ввод → пустой список
bad = _validate_json("это не JSON вообще")
assert bad == []
print("OK: мусорный JSON → []")

# Тест 4: снятие обёртки ```json
wrapped = _validate_json('```json\n[{"name":"Test","sure":false}]\n```')
assert len(wrapped) == 1
print("OK: снятие обёртки ```json работает")

# Тест 5: sure = False если поле отсутствует
no_sure = _validate_json('[{"name":"Аспирин"}]')
assert no_sure[0]["sure"] is False
print("OK: sure=False по умолчанию")

# Тест 6: конвертация PNG → JPEG (маленькая картинка 1×1)
from PIL import Image
import io
img = Image.new("RGB", (1, 1), color=(255, 0, 0))
buf = io.BytesIO()
img.save(buf, format="PNG")
png_bytes = buf.getvalue()
jpeg_bytes = _convert_to_jpeg(png_bytes)
assert jpeg_bytes[:3] == b"\xff\xd8\xff"  # JPEG magic bytes
print("OK: конвертация PNG → JPEG работает")

print()
print("Все тесты пройдены успешно!")
