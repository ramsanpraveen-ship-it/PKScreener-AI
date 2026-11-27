if __name__ == "__main__":

    from technical_engine import run_technical_analysis

    result = run_technical_analysis(
        symbol="TCS",
        period="2y"
    )

    print("\n========== DYNAMIC SYMBOL TEST ==========")

    print("Symbol:", result["symbol"])
    print("Ticker:", result["symbol"] + ".NS")

    print("\n========== SCREENING SUMMARY ==========")

    for key, value in result["screening_summary"].items():
        print(f"{key}: {value}")

    print("\n========== RELATIVE STRENGTH ==========")

    print(result["relative_strength_analysis"])

    print("\n========== TREND ANALYSIS ==========")

    print(result["trend_analysis"])

    print("\n========== VCP ANALYSIS ==========")

    print(
        "VCP Symbol:",
        result["contraction_analysis"]["symbol"]
    )

    print(
        "Contraction sequence:",
        result["contraction_analysis"]["contraction_sequence"]
    )

    print("\n========== FINAL STATUS ==========")

    print(result["screening_summary"]["candidate_status"])
