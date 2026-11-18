import React from "react";
import { StyleSheet, Text, View, ScrollView, TouchableOpacity } from "react-native";
import { translations } from "../translations";

// Статусы от сервера (backend/drugs/status.py). У каждой карточки ровно один.
const STATUS_FOUND = "found";                      // найдено в справочнике
const STATUS_UNSURE = "unsure";                    // «Не уверен, возможно это …»
const STATUS_NOT_IN_DIRECTORY = "not_in_directory"; // нет в справочнике

// Итоговый статус рецепта
const RECIPE_ALL_FOUND = "all_found";
const RECIPE_PARTLY_FOUND = "partly_found";
const RECIPE_NONE_FOUND = "none_found";

export default function ResultScreen({ result, lang, onBack }) {
  const t = translations[lang || "ru"];
  const drugs = result?.drugs || [];
  const advice = result?.advice || []; // «Советы врача»: это не лекарства

  // Для каждого статуса карточки: текст значка и его стиль (значок один)
  const badgeByStatus = {
    [STATUS_FOUND]: { text: t.statusFound, box: styles.badgeFound, label: styles.badgeTextFound },
    [STATUS_UNSURE]: { text: t.statusUnsure, box: styles.badgeUnsure, label: styles.badgeTextUnsure },
    [STATUS_NOT_IN_DIRECTORY]: { text: t.statusNotInDirectory, box: styles.badgeMissing, label: styles.badgeTextMissing },
  };

  // Итог по рецепту: текст и стиль плашки
  const bannerByRecipe = {
    [RECIPE_ALL_FOUND]: { text: t.recipeAllFound, box: styles.bannerGood, label: styles.bannerTextGood },
    [RECIPE_PARTLY_FOUND]: { text: t.recipePartlyFound, box: styles.bannerWarn, label: styles.bannerTextWarn },
    [RECIPE_NONE_FOUND]: { text: t.recipeNoneFound, box: styles.bannerBad, label: styles.bannerTextBad },
  };
  const banner = bannerByRecipe[result?.recipe_status];

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

      {/* Итог по всему рецепту: один статус */}
      {banner && (
        <View style={[styles.banner, banner.box]}>
          <Text style={[styles.bannerText, banner.label]}>{banner.text}</Text>
        </View>
      )}

      <Text style={styles.sectionHeader}>
        {t.foundDrugs} ({drugs.length}):
      </Text>

      {drugs.map((drug, index) => {
        const badge = badgeByStatus[drug.status] || badgeByStatus[STATUS_NOT_IN_DIRECTORY];
        return (
        <View key={index} style={styles.drugCard}>
          <View style={styles.drugHeader}>
            <Text style={styles.drugName}>{drug.name || "—"}</Text>
            {/* Один значок на карточке: он зависит только от drug.status */}
            <View style={[styles.badge, badge.box]}>
              <Text style={[styles.badgeText, badge.label]}>{badge.text}</Text>
            </View>
          </View>

          {/* Если не найдено уверенно — пояснение от сервера (уже на нужном языке) */}
          {drug.status !== STATUS_FOUND && drug.note && (
            <View style={styles.unsureBox}>
              <Text style={styles.unsureText}>{drug.note}</Text>
            </View>
          )}

          {/* Если название в карточке не совпадает с тем, что AI прочитал буквально, показываем мелко, что написано в рецепте */}
          {drug.read_as && (drug.name || "").trim().toLowerCase() !== drug.read_as.trim().toLowerCase() && (
            <Text style={styles.readAs}>
              {t.readAsLabel}: {drug.read_as}
            </Text>
          )}

          {drug.form && (
            <View style={styles.row}>
              <Text style={styles.label}>{t.formLabel}:</Text>
              <Text style={styles.val}>{drug.form}</Text>
            </View>
          )}

          {/* «Для чего» берётся из справочника. В справочнике текст только на русском */}
          {drug.indication && (
            <View style={styles.row}>
              <Text style={styles.label}>{t.indicationLabel}:</Text>
              <Text style={styles.val}>{drug.indication}</Text>
            </View>
          )}

          {/* Как написал врач: показываем ровно то, что прочитал AI */}
          {(drug.dose || drug.frequency || drug.duration) && (
            <View style={styles.doctorBox}>
              <Text style={styles.doctorTitle}>{t.writtenByDoctor}</Text>
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
          )}

          {/* Цена и аналоги показываются, только если лекарство найдено в справочнике.
              Если цену ещё не проверили, сервер присылает price_kzt = null */}
          {drug.status === STATUS_FOUND ? (
            <View>
              <View style={styles.row}>
                <Text style={styles.label}>💰 {t.priceLabel}:</Text>
                <Text style={styles.price}>
                  {drug.price_kzt != null ? `${drug.price_kzt} ${t.currency}` : t.priceUnknown}
                </Text>
              </View>

              <Text style={styles.analogsTitle}>💊 {t.analogsLabel}:</Text>
              {drug.analogs && drug.analogs.length > 0 ? (
                drug.analogs.map((analog, i) => (
                  <View key={i} style={styles.analogRow}>
                    <Text style={styles.analogName}>{analog.name}</Text>
                    <Text style={styles.analogPrice}>
                      {analog.price_kzt != null ? `${analog.price_kzt} ${t.currency}` : t.priceUnknown}
                    </Text>
                  </View>
                ))
              ) : (
                <Text style={styles.noAnalogs}>{t.noAnalogs}</Text>
              )}
            </View>
          ) : null}
        </View>
        );
      })}

      {/* Советы врача (тёплая вода, полоскание, режим…) — отдельно от лекарств */}
      {advice.length > 0 && (
        <View style={styles.adviceCard}>
          <Text style={styles.adviceTitle}>{t.adviceTitle}</Text>
          {advice.map((tip, i) => (
            <Text key={i} style={styles.adviceItem}>• {tip}</Text>
          ))}
        </View>
      )}

      {/* Обязательный медицинский дисклеймер на выбранном языке (kk/ru) */}
      <View style={styles.disclaimerCard}>
        <Text style={styles.disclaimerTitle}>⚠️ {t.disclaimerTitle}</Text>
        <Text style={styles.disclaimerBody}>
          {result?.disclaimer?.[lang || "ru"] || t.disclaimerText}
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
  badgeFound: {
    backgroundColor: "#DCFCE7",
  },
  badgeUnsure: {
    backgroundColor: "#FEF3C7",
  },
  badgeMissing: {
    backgroundColor: "#FEE2E2",
  },
  badgeText: {
    fontSize: 12,
    fontWeight: "600",
  },
  badgeTextFound: {
    color: "#15803D",
  },
  badgeTextUnsure: {
    color: "#B45309",
  },
  badgeTextMissing: {
    color: "#B91C1C",
  },
  banner: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  bannerText: {
    fontSize: 15,
    fontWeight: "600",
  },
  bannerGood: { backgroundColor: "#ECFDF5", borderColor: "#A7F3D0" },
  bannerTextGood: { color: "#065F46" },
  bannerWarn: { backgroundColor: "#FEF3C7", borderColor: "#FCD34D" },
  bannerTextWarn: { color: "#92400E" },
  bannerBad: { backgroundColor: "#FEE2E2", borderColor: "#FCA5A5" },
  bannerTextBad: { color: "#991B1B" },
  adviceCard: {
    backgroundColor: "#EFF6FF",
    borderColor: "#BFDBFE",
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    marginTop: 4,
    marginBottom: 12,
  },
  adviceTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: "#1E3A8A",
    marginBottom: 6,
  },
  adviceItem: {
    fontSize: 14,
    color: "#1E40AF",
    marginTop: 4,
    lineHeight: 20,
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
  readAs: {
    fontSize: 12,
    color: "#94A3B8",
    marginBottom: 4,
  },
  unsureBox: {
    backgroundColor: "#FEF3C7",
    borderRadius: 8,
    padding: 10,
    marginBottom: 6,
  },
  unsureText: {
    fontSize: 14,
    color: "#92400E",
    fontWeight: "600",
  },
  doctorBox: {
    backgroundColor: "#F1F5F9",
    borderRadius: 10,
    padding: 10,
    marginTop: 10,
  },
  doctorTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: "#334155",
  },
  price: {
    flex: 1,
    fontSize: 16,
    color: "#047857",
    fontWeight: "700",
  },
  analogsTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: "#64748B",
    marginTop: 12,
    marginBottom: 4,
  },
  analogRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
  },
  analogName: {
    fontSize: 14,
    color: "#1E293B",
    flex: 1,
  },
  analogPrice: {
    fontSize: 14,
    color: "#047857",
    fontWeight: "600",
  },
  noAnalogs: {
    fontSize: 13,
    color: "#94A3B8",
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

