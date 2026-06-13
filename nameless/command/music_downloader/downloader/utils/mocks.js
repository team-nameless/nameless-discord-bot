var global = this;
var window = this;

function URLSearchParams(queryString) {
    res = __url_parseSearchParams(queryString || '');
    this._params = res ? JSON.parse(res) : {};
    return this;
}

URLSearchParams.prototype.has = function (name) {
    if (this._params && name in this._params) {
        return true;
    }
    return false;
};

URLSearchParams.prototype.get = function (name) {
    if (this._params && name in this._params) {
        return this._params[name];
    }
    return null;
};

URLSearchParams.prototype.set = function (name, value) {
    if (!this._params) {
        this._params = {};
    }
    this._params[name] = value;
};

URLSearchParams.prototype.toString = function () {
    var parts = [];
    for (var key in this._params) {
        parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(this._params[key]));
    }
    return parts.join('&');
};

global.URLSearchParams = URLSearchParams;

// -------------------- //

function URL(urlStr) {
    urlStr = String(urlStr);
    var res = __url_parse(urlStr);
    if (!res) {
        throw new TypeError("Failed to construct 'URL': Invalid URL");
    }
    var obj = JSON.parse(res);
    this.href = obj.href;
    this.protocol = obj.protocol;
    this.hostname = obj.hostname;
    this.port = obj.port;
    this.pathname = obj.pathname;
    this.search = obj.search;
    this.hash = obj.hash;
    this.searchParams = new URLSearchParams(this.search);

    return this;
}

URL.prototype.toString = function () {
    return this.href;
};

URL.prototype.toJSON = function () {
    return this.href;
};

global.URL = URL;

// -------------------- //

var http = {
    get: function (url, headers) {
        var res = __http_get(String(url), headers ? JSON.stringify(headers) : null);
        return JSON.parse(res);
    },
    post: function (url, body, headers) {
        var res = __http_post(String(url), body, headers ? JSON.stringify(headers) : null);
        return JSON.parse(res);
    },
    clearCookies: __http_clearCookies
};

var file = {
    exists: __file_exists,
    getSize: function (path) {
        var res = __file_getSize(path);
        return JSON.parse(res);
    },
    delete: function (path) {
        var res = __file_delete(path);
        return JSON.parse(res);
    },
    readBytes: function (path, options) {
        var res = __file_readBytes(path, options ? JSON.stringify(options) : null);
        return JSON.parse(res);
    },
    writeBytes: function (path, data, options) {
        var res = __file_writeBytes(path, data, options ? JSON.stringify(options) : null);
        return JSON.parse(res);
    },
    download: function (url, outputPath, options) {
        options = options || {};
        var hasProgress = typeof options.onProgress === 'function';
        if (!hasProgress && typeof global.__active_download_progress === 'function') {
            options.onProgress = global.__active_download_progress;
            hasProgress = true;
        }
        var progressId = null;
        if (hasProgress) {
            progressId = "dl_" + Math.random().toString(36).substring(2);
            __progress_callbacks[progressId] = options.onProgress;
        }

        var cleanOpts = {};
        if (options.headers) cleanOpts.headers = options.headers;

        var res = __file_download(String(url), outputPath, JSON.stringify(cleanOpts), progressId);
        if (progressId) {
            delete __progress_callbacks[progressId];
        }
        return JSON.parse(res);
    }
};

var gobackend = {
    sanitizeFilename: __gobackend_sanitizeFilename,
    getAudioQuality: function (path) {
        var res = __gobackend_getAudioQuality(path);
        return JSON.parse(res);
    },
    checkISRCExists: function (outputDir, isrc) {
        var res = __gobackend_checkISRCExists(outputDir, isrc);
        return JSON.parse(res);
    },
    getLocalTime: function () {
        var res = __gobackend_getLocalTime();
        return JSON.parse(res);
    },
    getLyricsLRC: function (spotifyId, title, artist, album, durationMs) {
        var res = __gobackend_getLyricsLRC(
            spotifyId || "",
            title || "",
            artist || "",
            album || "",
            Number(durationMs || 0)
        );
        return JSON.parse(res);
    }
};

var utils = {
    appUserAgent: __utils_appUserAgent,
    randomUserAgent: __utils_randomUserAgent,
    appVersion: __utils_appVersion,
    base64Decode: __utils_base64Decode,
    base64Encode: __utils_base64Encode,
    isDownloadCancelled: __utils_isDownloadCancelled,
    hmacSHA1: function (key, data) {
        var res = __utils_hmacSHA1(JSON.stringify(key), JSON.stringify(data));
        return JSON.parse(res);
    },
    parseJSON: function (s) {
        return JSON.parse(s);
    },
    stringifyJSON: function (obj) {
        return JSON.stringify(obj);
    },
    md5: __utils_md5,
    sha256: __utils_sha256,
    hmacSHA256: __utils_hmacSHA256,
    hmacSHA256Base64: __utils_hmacSHA256Base64,
    encryptBlockCipher: function (data, options) {
        var res = __utils_encryptBlockCipher(data, JSON.stringify(options));
        return JSON.parse(res);
    },
    decryptBlockCipher: function (data, options) {
        var res = __utils_decryptBlockCipher(data, JSON.stringify(options));
        return JSON.parse(res);
    },
    sleep: __utils_sleep
};

var storage = {
    get: function (key) {
        var res = __storage_get(key);
        return JSON.parse(res);
    },
    set: function (key, value) {
        __storage_set(key, JSON.stringify(value));
    },
    remove: __storage_remove
};

var credentials = {
    store: function (key, value) {
        __credentials_store(key, JSON.stringify(value));
    },
    get: function (key) {
        var res = __credentials_get(key);
        return JSON.parse(res);
    },
    has: __credentials_has,
    remove: __credentials_remove
};

var auth = {
    openAuthUrl: __auth_openAuthUrl,
    getAuthCode: __auth_getAuthCode,
    setAuthCode: function (tokens) {
        __auth_setAuthCode(JSON.stringify(tokens));
    },
    isAuthenticated: __auth_isAuthenticated,
    getTokens: function () {
        var res = __auth_getTokens();
        return JSON.parse(res);
    },
    clearAuth: __auth_clearAuth
};

var matching = {
    compareStrings: __matching_compareStrings,
    compareDuration: __matching_compareDuration,
    normalizeString: __matching_normalizeString
};

var log = {
    info: function () { __log_info(Array.prototype.join.call(arguments, ' ')); },
    debug: function () { __log_debug(Array.prototype.join.call(arguments, ' ')); },
    error: function () { __log_error(Array.prototype.join.call(arguments, ' ')); },
    warn: function () { __log_warn(Array.prototype.join.call(arguments, ' ')); }
};
var console = log;

var __progress_callbacks = {};
function __trigger_progress(progressId, written, total) {
    var cb = __progress_callbacks[progressId];
    if (cb) {
        try {
            cb(written, total);
        } catch (e) { }
    }
}

// does quickjs support fetch natively?
function fetch(url, options) {
    options = options || {};
    var method = (options.method || 'GET').toUpperCase();
    var headers = options.headers || {};
    var body = options.body || null;

    var response;
    if (method === 'GET' || method === 'HEAD') {
        response = http.get(url, headers);
    } else if (method === 'POST') {
        response = http.post(url, body, headers);
    } else {
        throw new Error('Unsupported HTTP method: ' + method);
    }

    var responseObj = {
        ok: response.ok || false,
        status: response.status || response.statusCode || 0,
        statusText: response.status >= 200 && response.status < 300 ? 'OK' : 'ERROR',
        headers: response.headers || {},
        body: response.body || '',
        text: function () {
            return this.body;
        },
        json: function () {
            try {
                return JSON.parse(this.body);
            } catch (e) {
                throw new Error('Invalid JSON response');
            }
        },
        arrayBuffer: function () {
            return this.body;
        },
        blob: function () {
            return this.body;
        }
    };

    return responseObj;
}
