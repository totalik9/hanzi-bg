# Room keeps generated schema in schemas/ for migration diffing.
-keep class bg.hanzi.learn.data.db.** { *; }

# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class bg.hanzi.learn.** {
    *** Companion;
}
-keepclasseswithmembers class bg.hanzi.learn.** {
    kotlinx.serialization.KSerializer serializer(...);
}
