import React from "react";
import { StyleSheet, Text, View, ScrollView, TouchableOpacity } from "react-native";
import { translations } from "../translations";

export default function ResultScreen({ result, lang, onBack }) {
  const t = translations[lang || "ru"];
  const drugs = result?.drugs || [];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <TouchableOpacity style={styles.backBtn} onPress={onBack}>
        <Text style={styles.backBtnText}>{t.backBtn}</Text>
      </TouchableOpacity>

      <Text style={styles.title}>{t.resultTitle}</Text>

      {/* Статус получения фото сервером */}
      <View style={styles.statusBox}>
        <Text style={styles.statusText}>{result?.message || t.statusReceived}</Text>
        {result?.received_size_kb && (
          <Text style={styles.statusSub}>
            {t.statusSize}: {result.received_size_kb} КБ
          </Text>
        )}
      </View>

      <Text style={styles.sectionHeader}>
        {t.foundDrugs} ({drugs.length}):
      </Text>

      {drugs.map((drug, index) => (
        <View key={index} style={styles.drugCard}>
          <View style={styles.drugHeader}>
            <Text style={styles.drugName}>{drug.name || "—"}</Text>
            <View style={[styles.badge, drug.sure ? styles.badgeSure : styles.badgeUnsure]}>
              <Text style={[styles.badgeText, drug.sure ? styles.badgeTextSure : styles.badgeTextUnsure]}>
                {drug.sure ? t.sureYes : t.sureNo}
              </Text>
            </View>
          </View>

          {drug.form && (
            <View style={styles.row}>
              <Text style={styles.label}>{t.formLabel}:</Text>
              <Text style={styles.val}>{drug.form}</Text>
            </View>
          )}

          {drug.dose && (
            <View style={styles.row}>
              <Text style={styles.label}>{t.doseLabel}:</Text>
              <Text style={styles.val}>{drug.dose}</Text>
            </View>
          )}

          {drug.frequency && (
            <View style={styles.row}>
              <Text style={styles.label}>{t.freqLabel}:</Text>
              <Text style={styles.val}>{drug.frequency}</Text>
            </View>
          )}

          {drug.duration && (
            <View style={styles.row}>
              <Text style={styles.label}>{t.durLabel}:</Text>
              <Text style={styles.val}>{drug.duration}</Text>
            </View>
          )}
        </View>
      ))}

      {/* Обязательный медицинский дисклеймер */}
      <View style={styles.disclaimerCard}>
        <Text style={styles.disclaimerTitle}>⚠️ {t.disclaimerTitle}</Text>
        <Text style={styles.disclaimerBody}>{result?.disclaimer || t.disclaimerText}</Text>
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
    marginBottom: 16,
  },
  statusBox: {
    backgroundColor: "#ECFDF5",
    borderColor: "#A7F3D0",
    borderWidth: 1,
    borderRadius: 12,
    padding: 14,
    marginBottom: 20,
  },
  statusText: {
    fontSize: 15,
    fontWeight: "600",
    color: "#065F46",
  },
  statusSub: {
    fontSize: 13,
    color: "#047857",
    marginTop: 4,
  },
  sectionHeader: {
    fontSize: 18,
    fontWeight: "700",
    color: "#1E293B",
    marginBottom: 12,
  },
  drugCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 5,
    elevation: 2,
  },
  drugHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 10,
    flexWrap: "wrap",
    gap: 8,
  },
  drugName: {
    fontSize: 18,
    fontWeight: "700",
    color: "#0F172A",
    flex: 1,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  badgeSure: {
    backgroundColor: "#DCFCE7",
  },
  badgeUnsure: {
    backgroundColor: "#FEF3C7",
  },
  badgeText: {
    fontSize: 12,
    fontWeight: "600",
  },
  badgeTextSure: {
    color: "#15803D",
  },
  badgeTextUnsure: {
    color: "#B45309",
  },
  row: {
    flexDirection: "row",
    marginTop: 6,
  },
  label: {
    width: 130,
    fontSize: 14,
    color: "#64748B",
    fontWeight: "500",
  },
  val: {
    flex: 1,
    fontSize: 14,
    color: "#1E293B",
    fontWeight: "600",
  },
  disclaimerCard: {
    backgroundColor: "#FEF2F2",
    borderColor: "#FCA5A5",
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    marginTop: 16,
  },
  disclaimerTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: "#991B1B",
    marginBottom: 4,
  },
  disclaimerBody: {
    fontSize: 13,
    color: "#7F1D1D",
    lineHeight: 18,
  },
});
