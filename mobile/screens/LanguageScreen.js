import React from "react";
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { translations } from "../translations";

export default function LanguageScreen({ currentLang, onSelectLanguage }) {
  const t = translations[currentLang || "ru"];

  return (
    <View style={styles.container}>
      <Text style={styles.icon}>💊</Text>
      <Text style={styles.title}>ReceptAI</Text>
      <Text style={styles.subtitle}>{t.appSubtitle}</Text>

      <View style={styles.card}>
        <Text style={styles.prompt}>{t.selectLang}</Text>

        <TouchableOpacity
          style={[styles.btn, currentLang === "kk" && styles.btnActive]}
          onPress={() => onSelectLanguage("kk")}
        >
          <Text style={[styles.btnText, currentLang === "kk" && styles.btnTextActive]}>
            🇰🇿 Қазақша
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, currentLang === "ru" && styles.btnActive]}
          onPress={() => onSelectLanguage("ru")}
        >
          <Text style={[styles.btnText, currentLang === "ru" && styles.btnTextActive]}>
            🇷🇺 Русский
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F5F7FA",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  icon: {
    fontSize: 64,
    marginBottom: 8,
  },
  title: {
    fontSize: 32,
    fontWeight: "bold",
    color: "#1E293B",
  },
  subtitle: {
    fontSize: 16,
    color: "#64748B",
    marginTop: 4,
    marginBottom: 32,
    textAlign: "center",
  },
  card: {
    width: "100%",
    maxWidth: 360,
    backgroundColor: "#FFFFFF",
    borderRadius: 16,
    padding: 24,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 10,
    elevation: 3,
  },
  prompt: {
    fontSize: 16,
    fontWeight: "600",
    color: "#334155",
    marginBottom: 20,
    textAlign: "center",
  },
  btn: {
    backgroundColor: "#F1F5F9",
    borderRadius: 12,
    paddingVertical: 14,
    marginVertical: 6,
    alignItems: "center",
  },
  btnActive: {
    backgroundColor: "#2563EB",
  },
  btnText: {
    fontSize: 18,
    fontWeight: "600",
    color: "#1E293B",
  },
  btnTextActive: {
    color: "#FFFFFF",
  },
});
