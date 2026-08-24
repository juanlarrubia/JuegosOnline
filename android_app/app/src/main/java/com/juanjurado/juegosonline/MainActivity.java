package com.juanjurado.juegosonline;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.annotation.NonNull;

import com.google.android.gms.ads.AdError;
import com.google.android.gms.ads.AdRequest;
import com.google.android.gms.ads.FullScreenContentCallback;
import com.google.android.gms.ads.LoadAdError;
import com.google.android.gms.ads.MobileAds;
import com.google.android.gms.ads.interstitial.InterstitialAd;
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback;

public class MainActivity extends Activity {

    private static final String HOME = "https://juegosonline.onrender.com";

    // ID OFICIAL DE PRUEBA DE GOOGLE PARA INTERSTICIALES
    private static final String TEST_INTERSTITIAL_ID =
            "ca-app-pub-3940256099942544/1033173712";

    private WebView webView;
    private InterstitialAd interstitialAd;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Inicializar Google Mobile Ads
        MobileAds.initialize(this, initializationStatus -> {
            Log.d("ADMOB", "AdMob inicializado");
        });

        // Preparar un anuncio intersticial de prueba
        loadInterstitial();

        // Crear WebView
        webView = new WebView(this);
        setContentView(webView);

        // Configuración del WebView
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);

        // Cookies
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, true);

        webView.setWebChromeClient(new WebChromeClient());

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(
                    WebView view,
                    WebResourceRequest request
            ) {
                return false;
            }
        });

        if (savedInstanceState == null) {
            webView.loadUrl(HOME);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void loadInterstitial() {

        AdRequest adRequest = new AdRequest.Builder().build();

        InterstitialAd.load(
                this,
                TEST_INTERSTITIAL_ID,
                adRequest,
                new InterstitialAdLoadCallback() {

                    @Override
                    public void onAdLoaded(
                            @NonNull InterstitialAd ad
                    ) {
                        interstitialAd = ad;

                        Log.d(
                                "ADMOB",
                                "ANUNCIO INTERSTICIAL CARGADO"
                        );

                        interstitialAd.setFullScreenContentCallback(
                                new FullScreenContentCallback() {

                                    @Override
                                    public void onAdDismissedFullScreenContent() {
                                        interstitialAd = null;

                                        // Preparar el siguiente anuncio
                                        loadInterstitial();
                                    }

                                    @Override
                                    public void onAdFailedToShowFullScreenContent(
                                            @NonNull AdError adError
                                    ) {
                                        interstitialAd = null;
                                        loadInterstitial();
                                    }
                                }
                        );
                    }

                    @Override
                    public void onAdFailedToLoad(
                            @NonNull LoadAdError loadAdError
                    ) {
                        interstitialAd = null;

                        Log.e(
                                "ADMOB",
                                "ERROR AL CARGAR ANUNCIO: "
                                        + loadAdError.getMessage()
                        );
                    }
                }
        );
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}