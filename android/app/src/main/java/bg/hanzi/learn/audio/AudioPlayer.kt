package bg.hanzi.learn.audio

import android.content.Context
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.exoplayer.ExoPlayer
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Single shared ExoPlayer for all pronunciation clips.
 *
 * One player instance is kept for the whole process: spinning up an
 * ExoPlayer per clip costs ~10 MB of heap and noticeable latency, which
 * matters on an 8 GB device where the app may be competing with a browser.
 * Media3 is released when the app process dies.
 */
@Singleton
class AudioPlayer @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    private val _playing = MutableStateFlow<String?>(null)
    val playing: StateFlow<String?> = _playing.asStateFlow()

    @OptIn(UnstableApi::class)
    private val player: ExoPlayer by lazy {
        ExoPlayer.Builder(context)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
                    .setUsage(C.USAGE_MEDIA)
                    .build(),
                /* handleAudioFocus = */ false,
            )
            // DefaultDataSource.Factory resolves asset:// URIs from the APK.
            .setMediaSourceFactory(
                androidx.media3.exoplayer.source.DefaultMediaSourceFactory(
                    DefaultDataSource.Factory(context),
                ),
            )
            .setHandleAudioBecomingNoisy(true)
            .build()
            .apply {
                addListener(object : Player.Listener {
                    override fun onPlaybackStateChanged(playbackState: Int) {
                        if (playbackState == Player.STATE_ENDED ||
                            playbackState == Player.STATE_IDLE
                        ) {
                            _playing.value = null
                        }
                    }

                    override fun onPlayerError(error: PlaybackException) {
                        _playing.value = null
                    }
                })
            }
    }

    /** Plays an asset-relative audio file, e.g. "audio/abc123.mp3". */
    @OptIn(UnstableApi::class)
    fun play(assetPath: String) {
        if (_playing.value == assetPath && player.isPlaying) {
            player.pause()
            _playing.value = null
            return
        }
        try {
            // DefaultDataSource resolves asset:// URIs from the APK.
            player.setMediaItem(MediaItem.fromUri("asset:///$assetPath"))
            player.prepare()
            player.play()
            _playing.value = assetPath
        } catch (e: Exception) {
            _playing.value = null
        }
    }

    fun stop() {
        player.stop()
        _playing.value = null
    }
}
