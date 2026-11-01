package com.kacyraho.lightnovel

import android.os.Build
import org.junit.Assume
import org.junit.rules.TestRule
import org.junit.runner.Description
import org.junit.runners.model.Statement

class SkipOnMiuiRule : TestRule {
    override fun apply(base: Statement, description: Description): Statement =
        object : Statement() {
            override fun evaluate() {
                val manufacturer = Build.MANUFACTURER.orEmpty()
                val brand = Build.BRAND.orEmpty()
                val miui = manufacturer.contains("Xiaomi", ignoreCase = true) ||
                    brand.contains("Redmi", ignoreCase = true) ||
                    brand.contains("Xiaomi", ignoreCase = true)
                Assume.assumeFalse(
                    "HyperOS 会拦截 instrumentation 启动 Activity；请在 AOSP/模拟器运行，" +
                        "或开启开发者选项里的后台活动启动许可",
                    miui,
                )
                base.evaluate()
            }
        }
}
