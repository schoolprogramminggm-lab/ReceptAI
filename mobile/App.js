import React, { useState } from "react";
import { StatusBar } from "expo-status-bar";
import { StyleSheet, SafeAreaView, View } from "react-native";

import LanguageScreen from "./screens/LanguageScreen";
import HomeScreen from "./screens/HomeScreen";
import ResultScreen from "./screens/ResultScreen";
import AboutScreen from "./screens/AboutScreen";

export default function App() {
  // Текущий экран: 'language' | 'home' | 'result' | 'about'
  const [currentScreen, setCurrentScreen] = useState("language");
  // Выбранный язык: 'ru' | 'kk'
  const [lang, setLang] = useState("ru");
  // Данные ответа сервера
  const [resultData, setResultData] = useState(null);

  // Выбор языка и переход на главный экран
  const handleSelectLanguage = (selectedLang) => {
    setLang(selectedLang);
    setCurrentScreen("home");
  };

  // Получен результат распознавания от backend
  const handleResultReceived = (data) => {
    setResultData(data);
    setCurrentScreen("result");
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="dark" />

      {currentScreen === "language" && (
        <LanguageScreen
          currentLang={lang}
          onSelectLanguage={handleSelectLanguage}
        />
      )}

      {currentScreen === "home" && (
        <HomeScreen
          lang={lang}
          onChangeLang={() => setCurrentScreen("language")}
          onOpenAbout={() => setCurrentScreen("about")}
          onResultReceived={handleResultReceived}
        />
      )}

      {currentScreen === "result" && (
        <ResultScreen
          result={resultData}
          lang={lang}
          onBack={() => setCurrentScreen("home")}
        />
      )}

      {currentScreen === "about" && (
        <AboutScreen
          lang={lang}
          onBack={() => setCurrentScreen("home")}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F8FAFC",
  },
});
