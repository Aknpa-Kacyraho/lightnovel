package com.kacyraho.lightnovel.feature.settings

/**
 * 设置页只接受少量深链目标；未知参数一律忽略，避免脏路由让页面乱滚。
 */
internal object SettingsFocus {
    const val BACKUP = "backup"

    fun parse(raw: String?): String? = raw?.trim()?.takeIf { it == BACKUP }
}
