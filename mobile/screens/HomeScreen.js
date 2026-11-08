import React, { useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  Alert,
  ScrollView,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { translations } from "../translations";

export default function HomeScreen({
  lang,
  onChangeLang,
  onOpenAbout,
  onResultReceived,
}) {
  const t = translations[lang || "ru"];
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);

  // Выбор фото из галереи
  const pickFromGallery = async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert("Внимание / Назар аударыңыз", "Требуется разрешение на доступ к галерее");
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: false,
        quality: 0.8,
      });

      if (!result.canceled && result.assets && result.assets.length > 0) {
        setPhotoUri(result.assets[0].uri);
      }
    } catch (e) {
      Alert.alert("Ошибка", e.message);
    }
  };

  // Сделать фото на камеру
  const takeWithCamera = async () => {
    try {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        Alert.alert("Внимание / Назар аударыңыз", "Требуется разрешение на использование камеры");
        return;
      }

      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: false,
        quality: 0.8,
      });

      if (!result.canceled && result.assets && result.assets.length > 0) {
        setPhotoUri(result.assets[0].uri);
      }
    } catch (e) {
      Alert.alert("Ошибка", e.message);
    }
  };

  // Отправка фото на сервер POST /api/read
  const sendPhoto = async () => {
    if (!photoUri) return;

    setLoading(true);
    try {
      const apiUrl = process.env.EXPO_PUBLIC_API_URL || "http://192.168.1.100:8000";

      const formData = new FormData();
      const filename = photoUri.split("/").pop() || "prescription.jpg";
      const match = /\.(\w+)$/.exec(filename);
      const type = match ? `image/${match[1]}` : "image/jpeg";

      formData.append("photo", {
        uri: photoUri,
        name: filename,
        type: type,
      });
      formData.append("lang", lang);

      const response = await fetch(`${apiUrl}/api/read`, {
        method: "POST",
        body: formData,
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();
      onResultReceived(data);
    } catch (error) {
      Alert.alert("Ошибка / Қателік", `${t.networkError}\n\n(${error.message})`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Верхняя панель: язык и переход О приложении */}
      <View style={styles.topBar}>
        <TouchableOpacity style={styles.langBadge} onPress={onChangeLang}>
          <Text style={styles.langBadgeText}>
            {lang === "kk" ? "🇰🇿 ҚАЗ" : "🇷🇺 РУС"} ▾
          </Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.aboutPill} onPress={onOpenAbout}>
          <Text style={styles.aboutPillText}>{t.aboutBtn}</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.title}>{t.homeTitle}</Text>
      <Text style={styles.subtitle}>{t.homeSubtitle}</Text>

      {/* Превью выбранного фото или кнопки выбора */}
      {photoUri ? (
        <View style={styles.previewContainer}>
          <Image source={{ uri: photoUri }} style={styles.previewImage} resizeMode="contain" />
          <TouchableOpacity
            style={styles.btnSecondary}
            onPress={() => setPhotoUri(null)}
            disabled={loading}
          >
            <Text style={styles.btnSecondaryText}>{t.changePhoto}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.actionsBox}>
          <TouchableOpacity style={styles.actionBtn} onPress={takeWithCamera}>
            <Text style={styles.actionBtnIcon}>📸</Text>
            <Text style={styles.actionBtnText}>{t.takePhoto}</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.actionBtn} onPress={pickFromGallery}>
            <Text style={styles.actionBtnIcon}>🖼</Text>
            <Text style={styles.actionBtnText}>{t.pickGallery}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Кнопка отправки на распознавание */}
      {photoUri && (
        <TouchableOpacity
          style={[styles.btnPrimary, loading && styles.btnDisabled]}
          onPress={sendPhoto}
          disabled={loading}
        >
          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color="#FFFFFF" />
              <Text style={styles.btnPrimaryText}>{t.sending}</Text>
            </View>
          ) : (
            <Text style={styles.btnPrimaryText}>{t.sendBtn}</Text>
          )}
        </TouchableOpacity>
      )}

      {/* Памятка по безопасности */}
      <View style={styles.infoBanner}>
        <Text style={styles.infoBannerText}>
          🔒 Фото обрабатывается в памяти и не сохраняется на диск
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F8FAFC",
  },
  content: {
    padding: 20,
    paddingTop: 50,
    paddingBottom: 40,
  },
  topBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 20,
  },
  langBadge: {
    backgroundColor: "#E2E8F0",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  langBadgeText: {
    fontSize: 14,
    fontWeight: "700",
    color: "#1E293B",
  },
  aboutPill: {
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  aboutPillText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#2563EB",
  },
  title: {
    fontSize: 26,
    fontWeight: "bold",
    color: "#0F172A",
  },
  subtitle: {
    fontSize: 14,
    color: "#64748B",
    marginTop: 6,
    marginBottom: 24,
  },
  actionsBox: {
    gap: 16,
    marginBottom: 24,
  },
  actionBtn: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#E2E8F0",
    borderStyle: "dashed",
  },
  actionBtnIcon: {
    fontSize: 40,
    marginBottom: 8,
  },
  actionBtnText: {
    fontSize: 17,
    fontWeight: "600",
    color: "#1E293B",
  },
  previewContainer: {
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    padding: 12,
    alignItems: "center",
    marginBottom: 20,
    borderWidth: 1,
    borderColor: "#E2E8F0",
  },
  previewImage: {
    width: "100%",
    height: 300,
    borderRadius: 10,
    backgroundColor: "#0F172A",
  },
  btnSecondary: {
    marginTop: 12,
    paddingVertical: 8,
  },
  btnSecondaryText: {
    fontSize: 15,
    fontWeight: "600",
    color: "#475569",
  },
  btnPrimary: {
    backgroundColor: "#2563EB",
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#2563EB",
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  btnDisabled: {
    backgroundColor: "#94A3B8",
  },
  btnPrimaryText: {
    fontSize: 18,
    fontWeight: "bold",
    color: "#FFFFFF",
    marginLeft: 8,
  },
  loadingRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  infoBanner: {
    marginTop: 30,
    alignItems: "center",
  },
  infoBannerText: {
    fontSize: 12,
    color: "#94A3B8",
  },
});
