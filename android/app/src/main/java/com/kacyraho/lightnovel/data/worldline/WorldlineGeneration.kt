package com.kacyraho.lightnovel.data.worldline

data class WorldlineLengthOption(
    val id: String,
    val label: String,
    val rangeLabel: String,
    val minChars: Int,
    val promptMin: Int,
    val targetChars: Int,
    val promptMax: Int,
    val maxChars: Int,
    val maxTokens: Int,
)

data class WorldlineCreativityOption(
    val id: String,
    val label: String,
    val hint: String,
    val temperature: Double,
)

object WorldlineGeneration {
    val lengthOptions: List<WorldlineLengthOption> = listOf(
        WorldlineLengthOption(
            id = "short",
            label = "短",
            rangeLabel = "800–1800 字",
            minChars = 300,
            promptMin = 800,
            targetChars = 1_200,
            promptMax = 1_800,
            maxChars = 2_500,
            maxTokens = 4_096,
        ),
        WorldlineLengthOption(
            id = "standard",
            label = "标准",
            rangeLabel = "1600–3200 字",
            minChars = 600,
            promptMin = 1_600,
            targetChars = 2_400,
            promptMax = 3_200,
            maxChars = 5_000,
            maxTokens = 8_192,
        ),
        WorldlineLengthOption(
            id = "long",
            label = "长",
            rangeLabel = "3000–6000 字",
            minChars = 1_200,
            promptMin = 3_000,
            targetChars = 4_200,
            promptMax = 6_000,
            maxChars = 8_000,
            maxTokens = 8_192,
        ),
    )

    val creativityOptions: List<WorldlineCreativityOption> = listOf(
        WorldlineCreativityOption(
            id = "stable",
            label = "稳定",
            hint = "更贴设定，少出意外",
            temperature = 0.55,
        ),
        WorldlineCreativityOption(
            id = "balanced",
            label = "均衡",
            hint = "设定与惊喜平衡",
            temperature = 0.8,
        ),
        WorldlineCreativityOption(
            id = "wild",
            label = "放开",
            hint = "更多临场发挥",
            temperature = 1.0,
        ),
    )

    fun length(id: String?): WorldlineLengthOption =
        lengthOptions.firstOrNull { it.id == id } ?: lengthOptions[1]

    fun creativity(id: String?): WorldlineCreativityOption =
        creativityOptions.firstOrNull { it.id == id } ?: creativityOptions[1]

    fun normalizeLength(id: String?): String = length(id).id

    fun normalizeCreativity(id: String?): String = creativity(id).id

    fun normalizeDirective(value: String): String = value.trim().take(2_000)
}
