'use strict';
module.exports = {
  ...require('./canonical'),
  ...require('./crypto'),
  ...require('./integrity'),
  predicate: require('./predicate'),
  UAP_VERSION: '2026-09-02',
};
