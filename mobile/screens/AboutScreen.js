import React from "react";
import { StyleSheet, Text, View, ScrollView, TouchableOpacity } from "react-native";
import { translations } from "../translations";

export default function AboutScreen({ lang, onBack }) {
  const t = translations[lang || "ru"];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <TouchableOpacity style={styles.backBtn} onPress={onBack}>
        <Text style={styles.backBtnText}>{t.backBtn}</Text>
      </TouchableOpacity>

      <Text style={styles.title}>{t.aboutHeader}</Text>

      <View style={styles.card}>
        <Text style={styles.metaBadge}>{t.aboutEvent}</Text>
        <Text style={styles.metaText}>👤 {t.aboutAuthor}</Text>
        <Text style={styles.metaText}>🎓 {t.aboutMentor}</Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>🎯 {t.aboutMissionTitle}</Text>
        <Text style={styles.sectionBody}>{t.aboutMissionText}</Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>🔒 {t.aboutSafetyTitle}</Text>
        <Text style={styles.sectionBody}>{t.aboutSafetyText}</Text>
      </View>

      <View style={styles.warningCard}>
        <Text style={styles.warningTitle}>⚠️ {t.disclaimerTitle}</Text>
        <Text style={styles.warningText}>{t.disclaimerText}</Text>
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
  backBtn: {
    alignSelf: "flex-start",
    backgroundColor: "#E2E8F0",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    marginBottom: 16,
  },
  backBtnText: {
    fontSize: 16,
    fontWeight: "600",
    color: "#1E293B",
  },
  title: {
    fontSize: 26,
    fontWeight: "bold",
    color: "#0F172A",
    marginBottom: 20,
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
  metaBadge: {
    fontSize: 13,
    fontWeight: "bold",
    color: "#2563EB",
    marginBottom: 8,
  },
  metaText: {
    fontSize: 15,
    color: "#334155",
    marginVertical: 2,
  },
  section: {
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: "#1E293B",
    marginBottom: 8,
  },
  sectionBody: {
    fontSize: 14,
    color: "#475569",
    lineHeight: 22,
  },
  warningCard: {
    backgroundColor: "#FEF2F2",
    borderWidth: 1,
    borderColor: "#FCA5A5",
    borderRadius: 14,
    padding: 16,
    marginTop: 8,
  },
  warningTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: "#991B1B",
    marginBottom: 6,
  },
  warningText: {
    fontSize: 13,
    color: "#7F1D1D",
    lineHeight: 19,
  },
});
