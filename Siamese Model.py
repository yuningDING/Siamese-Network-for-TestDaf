
def attention_3d_block(inputs):
    input_dim = int(inputs.shape[2])
    a = Permute((2, 1))(inputs)
    a = Dense(max_len, activation='softmax')(a)
    a_probs = Permute((2, 1))(a)
    output_attention_mul = layers.multiply([inputs, a_probs])
    print("op",output_attention_mul.get_shape().as_list())

    return output_attention_mul


def pearson_correlation(y_true, y_pred):
    # Pearson's correlation coefficient = covariance(X, Y) / (stdv(X) * stdv(Y))
    fs_pred = y_pred - K.mean(y_pred)
    fs_true = y_true - K.mean(y_true)
    covariance = K.mean(fs_true * fs_pred)

    stdv_true = K.std(y_true)
    stdv_pred = K.std(y_pred)

    return covariance / (stdv_true * stdv_pred)


def negative_pearson_correlation(y_true, y_pred):
    return -1 * pearson_correlation(y_true, y_pred)


from keras import layers
from keras import Input
from keras.models import Model, model_from_json
from keras.optimizers import Adadelta
from keras.callbacks import EarlyStopping
import keras.backend as K
import numpy as np
import matplotlib.pyplot as plt
from keras.layers.core import *

class SiameseModel:
    def __init__(self, use_cudnn_lstm=True, plot_model_architecture=False):
        n_hidden = max_len
        input_dim = 300
        time_steps = max_len

        lstm = layers.LSTM(n_hidden, unit_forget_bias=True,
                               kernel_initializer='he_normal',
                               kernel_regularizer='l2',
                               name='lstm_layer',return_sequences = True)
        cnn = layers.Conv1D(filters = 300, kernel_size = 10, padding = "same",  kernel_initializer='he_normal',
                               kernel_regularizer='l2')

        # Building the left branch of the model: inputs are variable-length sequences of vectors of size 128.
        left_input = Input(shape=(time_steps,input_dim), name='input_1')
        left_output = lstm(left_input)
        attention_left = attention_3d_block(left_output)
        attention_left = Flatten()(attention_left)


        # Building the right branch of the model: when you call an existing layer instance, you reuse its weights.
        right_1_input = Input(shape=(time_steps,input_dim), name='input_2')
        right_output1 = lstm(right_1_input)
        attention_right1 = attention_3d_block(right_output1)
        attention_right1 = Flatten()(attention_right1)

        
        right_2_input = Input(shape=(time_steps, input_dim), name='input_3')
        right_output2 = lstm(right_2_input)
        attention_right2 = attention_3d_block(right_output2)
        attention_right2 = Flatten()(attention_right2)
        
        right_3_input = Input(shape=(time_steps,input_dim), name='input_4')
        right_output3 = lstm(right_3_input)
        attention_right3 = attention_3d_block(right_output3)
        attention_right3 = Flatten()(attention_right3)

        # Builds the classifier on top
        merged1 = layers.subtract([attention_left, attention_right1])
        merged2 = layers.subtract([attention_left, attention_right2])
        merged3 = layers.subtract([attention_left, attention_right3])

        predictions1 = layers.Dense(1, activation='sigmoid', name='Similarity_layer1')(merged1)
        predictions2 = layers.Dense(1, activation='sigmoid', name='Similarity_layer2')(merged2)
        predictions3 = layers.Dense(1, activation='sigmoid', name='Similarity_layer3')(merged3)
        prediction = layers.concatenate([predictions1,predictions2,predictions3])
        
        predictions = layers.Dense(1, activation='sigmoid', name='Similarity_layer')(prediction)

        # Instantiating and training the model: when you train such a model, the weights of the LSTM layer are updated based on both inputs.
        self.model = Model([left_input, right_1_input, right_2_input, right_3_input], predictions)

        self.__compile()
        print(self.model.summary())


    def __compile(self):
        optimizer = Adadelta()  # gradient clipping is not there in Adadelta implementation in keras
        #        optimizer = 'adam'
        self.model.compile(loss='binary_crossentropy', optimizer=optimizer, metrics=[pearson_correlation])

    def fit(self, left_data, right_data1,right_data2,right_data3, targets, validation_data, epochs=5, batch_size=16):
        # The paper employ early stopping based on a validation, but they didn't mention parameters.
        early_stopping_monitor = EarlyStopping(monitor='val_pearson_correlation', mode='max', patience=20)
        #        callbacks = [early_stopping_monitor]
        callbacks = []
        history = self.model.fit([left_data, right_data1,right_data2,right_data3], targets, validation_data=validation_data,
                                 epochs=epochs, batch_size=batch_size
                                 , callbacks=callbacks)

        #self.visualize_metric(history.history, 'loss')
        #self.visualize_metric(history.history, 'pearson_correlation')

    def visualize_metric(self, history_dic, metric_name):
        plt.plot(history_dic[metric_name])
        legend = ['train']
        if 'val_' + metric_name in history_dic:
            plt.plot(history_dic['val_' + metric_name])
            legend.append('test')
        plt.title('model ' + metric_name)
        plt.ylabel(metric_name)
        plt.xlabel('epoch')
        plt.legend(legend, loc='upper left')
        plt.show()

    def predict(self, left_data, right_data1,right_data2,right_data3):
        return self.model.predict([left_data, right_data1,right_data2,right_data3])

    def evaluate(self, left_data, right_data1,right_data2,right_data3, targets, batch_size=128):
        return self.model.evaluate([left_data, right_data1,right_data2,right_data3], targets, batch_size=batch_size)

    def save(self, model_folder='./model/'):
        # serialize model to JSON
        model_json = self.model.to_json()
        with open(model_folder + 'model.json', 'w') as json_file:
            json_file.write(model_json)
        # serialize weights to HDF5
        self.model.save_weights(model_folder + 'model.h5')
        print('Saved model to disk')

    def save_pretrained_weights(self, model_wieghts_path='./model/pretrained_weights.h5'):
        self.model.save_weights(model_wieghts_path)
        print('Saved pretrained weights to disk')

    def load(self, model_folder='./model/'):
        # load json and create model
        json_file = open(model_folder + 'model.json', 'r')
        loaded_model_json = json_file.read()
        json_file.close()
        loaded_model = model_from_json(loaded_model_json)
        # load weights into new model
        loaded_model.load_weights(model_folder + 'model.h5')
        print('Loaded model from disk')

        self.model = loaded_model
        # loaded model should be compiled
        self.__compile()
        
    def load_pretrained_weights(self, model_wieghts_path='./model/pretrained_weights.h5'):
        # load weights into new model
        self.model.load_weights(model_wieghts_path)
        print('Loaded pretrained weights from disk')
        self.__compile()


from nltk import TreebankWordTokenizer

class Tokenizer:

    def __init__(self):
        self.tokenizer = TreebankWordTokenizer()

    def tokenize(self, sentence):
        tokens = self.tokenizer.tokenize(sentence)

        return tokens

class Vectorizer:

    def __init__(self, word_embeddings, tokenizer):
        self.word_embeddings = word_embeddings
        self.tokenizer = tokenizer

    def vectorize_sentence(self, sentence, threshold=-1):
        tokens = self.tokenizer.tokenize(sentence)

        if threshold > 0:
            # truncate answers to threshold tokens.
            tokens = tokens[:threshold]
        vector = []
        for token in tokens:
            if self.__valid_token(token):
                token = self.__normalize(token)
                try :
                    token_vector = self.word_embeddings[token]
                except KeyError:
                    continue

                if token_vector is not None:
                    vector.append(token_vector)
        return vector

    def vectorize_df(self, df):
        a_vectors = [self.vectorize_sentence(sentence) for sentence in df['studentAnswer']]
        b_vectors = [self.vectorize_sentence(sentence) for sentence in df['referenceAnswer']]
        c_vectors = [self.vectorize_sentence(sentence) for sentence in df['ref_1']]
        d_vectors = [self.vectorize_sentence(sentence) for sentence in df['ref_2']]
        gold = df['label'].tolist()

        return a_vectors, b_vectors,c_vectors,d_vectors, gold

    def __valid_token(self, token):
        if token in string.punctuation:
            return False
        return True

    def __normalize(self, token):
        token = token.lower()
        '''
        if token == "'s":
            token = 'is' # may be 'has' also
        elif token == "'re":
            token = 'are'
        elif token == "'t":
            token = 'not'
        elif token == "'m":
            token = 'am'
        elif token == "'d":
            token = 'would' # may be 'had' also
        '''
        return token.translate(str.maketrans('','', string.punctuation))


import pandas as pd
def read_TestDaf(filepath):
    df = pd.read_csv(filepath,sep='\t')
    df = df[["studentAnswer","referenceAnswer","ref_1", "ref_2", "accuracy"]]

    s = np.zeros(len(df))
    p = np.asarray(df['accuracy'],dtype=str)
    for i in range(len(p)):
        if p[i] != "0":
            s[i] = 1
    df['label'] = s
    df = df.drop('accuracy', 1)
    return df

# load embeddings
import bcolz
import numpy as np
import pickle

# TODO: change the path of embeddings
glove_path = "H:\dkpro\embed"
vectors = bcolz.open(f'{glove_path}/6B.de.300.dat')[:]
words = pickle.load(open(f'{glove_path}/6B.de.300_words.pkl', 'rb'))
word2idx = pickle.load(open(f'{glove_path}/6B.de.300_idx.pkl', 'rb'))

glove = {w: vectors[word2idx[w]] for w in words}

# TODO: change the path of input data
pathbase = "Input_TestDaF/"
#id_ft = ["00","01","02_1","02_2","03_3","03_4","04_1","04_5","05_6","05_7"]
id_ft00 = ["2.1","2.2","2.3","2.4","2.5","4.1","4.2","4.3","4.4","5.1","5.2","5.3","5.4"]
#id_ft01 = ["50.1","50.2","50.3","50.4","50.5","51.1","51.2","51.3","51.4","54.1","54.2","54.3","54.4"]
#id_ft02_1 = ["1.1","1.2","1.3","1.4","1.5","2.1","2.2","2.3","2.4","5.1","5.2","5.3","5.4"]
#id_ft02_2 = ["2.1","2.2","2.3","2.4","2.5","4.1","4.2","4.3","4.4","5.1","5.2","5.3","5.4"]
result_list = []


for item_id in id_ft00  :
    # main experiment starts here
    train_df = read_TestDaf(pathbase+"FT00/"+item_id+"_train.tsv")
    dev_df = read_TestDaf(pathbase+"FT00/"+item_id+"_dev.tsv")
    test_df = read_TestDaf(pathbase+"FT00/"+item_id+"_test.tsv")

    import json
    from keras.preprocessing.sequence import pad_sequences

    def read_data(file_path):
        samples = []
        with open(file_path) as f:
            for line in f:
                samples.append(json.loads(line))
        return samples

    def write_data(file_path, samples):
        with open(file_path, 'w') as outfile:
            for sample in samples:
                line = json.dumps(sample)
                outfile.write(line)
                outfile.write("\n")


    def pad_tensor(tensor, max_len, dtype='float32'):
        return pad_sequences(tensor, padding='post', dtype=dtype, maxlen=max_len)


    if __name__ == '__main__':
        tensor = [[[1,2,3],[4,5,6],[7,8,9]],
                  [[1,2,3]]]
        res = list(pad_tensor(tensor, 2))
        print(res)


    import string
    tokenizer = Tokenizer()
    vectorizer = Vectorizer(glove, tokenizer)

    train_a_vectors, train_b_vectors, train_c_vectors, train_d_vectors, train_gold = vectorizer.vectorize_df(train_df)
    train_max_a_length = len(max(train_a_vectors, key=len))
    #print(max(train_a_vectors, key=len))
    train_max_b_length = len(max(train_b_vectors, key=len))
    train_max_c_length = len(max(train_c_vectors, key=len))
    train_max_d_length = len(max(train_d_vectors, key=len))
    print('maximum number of tokens per sentence A in training set is %d' % train_max_a_length)
    print('maximum number of tokens per sentence B in training set is %d' % train_max_b_length)
    max_len = max([train_max_a_length, train_max_b_length,train_max_c_length,train_max_d_length])

    # padding
    train_a_vectors = pad_tensor(train_a_vectors, max_len)
    train_b_vectors = pad_tensor(train_b_vectors, max_len)
    train_c_vectors = pad_tensor(train_c_vectors, max_len)
    train_d_vectors = pad_tensor(train_d_vectors, max_len)


    #### development dataset ####
    # vectorizing
    dev_a_vectors, dev_b_vectors,dev_c_vectors, dev_d_vectors, dev_gold = vectorizer.vectorize_df(dev_df)
    dev_max_a_length = len(max(dev_a_vectors, key=len))
    dev_max_b_length = len(max(dev_b_vectors, key=len))
    dev_max_c_length = len(max(dev_c_vectors, key=len))
    dev_max_d_length = len(max(dev_d_vectors, key=len))
    print('maximum number of tokens per sentence A in dev set is %d' % dev_max_a_length)
    print('maximum number of tokens per sentence B in dev set is %d' % dev_max_b_length)
    #max_len = max([dev_max_a_length, dev_max_b_length, dev_max_c_length, dev_max_d_length])

    # padding
    dev_a_vectors = pad_tensor(dev_a_vectors, max_len)
    dev_b_vectors = pad_tensor(dev_b_vectors, max_len)
    dev_c_vectors = pad_tensor(dev_c_vectors, max_len)
    dev_d_vectors = pad_tensor(dev_d_vectors, max_len)

    print('Training the model ...')
    epochs = 50
    siamese = SiameseModel()

    validation_data = ([dev_a_vectors, dev_b_vectors,dev_c_vectors, dev_d_vectors ], dev_gold)

    #try:
    siamese.fit(train_a_vectors, train_b_vectors, train_c_vectors, train_d_vectors, train_gold, validation_data, epochs=epochs)
    #except ValueError:
        #continue


    from sklearn.metrics import mean_squared_error
    from scipy import stats

    print('Vectorizing testing dataset ...')
    test_a_vectors, test_b_vectors,test_c_vectors,test_d_vectors, test_gold = vectorizer.vectorize_df(test_df)
    test_max_a_length = len(max(test_a_vectors, key=len))
    test_max_b_length = len(max(test_b_vectors, key=len))
    test_max_c_length = len(max(test_c_vectors, key=len))
    test_max_d_length = len(max(test_d_vectors, key=len))
    print('maximum number of tokens per sentence A in testing set is %d' % test_max_a_length)
    print('maximum number of tokens per sentence B in testing set is %d' % test_max_b_length)

    # padding
    print('Padding testing dataset ...')
    test_a_vectors = pad_tensor(test_a_vectors, max_len)
    test_b_vectors = pad_tensor(test_b_vectors, max_len)
    test_c_vectors = pad_tensor(test_c_vectors, max_len)
    test_d_vectors = pad_tensor(test_d_vectors, max_len)

    print('Testing the model ...')
    result = siamese.evaluate(test_a_vectors, test_b_vectors,test_c_vectors, test_d_vectors, test_gold, 4906)


    y = siamese.predict(test_a_vectors, test_b_vectors, test_c_vectors, test_d_vectors)
    y = [i[0] for i in y]


    for i in range(len(y)):
        if y[i]>0.5:
            y[i] = 1
        else: y[i]= 0

    assert len(test_gold) == len(y)


    from sklearn.metrics import accuracy_score,confusion_matrix
    print('Accuracy =  %.2f' % accuracy_score(test_gold, y))
    result_list.append("****"+item_id+"****\nAccuracy =  %.2f'" % accuracy_score(test_gold, y)+"\n"+np.array_str(confusion_matrix(test_gold,y))+"\n")


f = open("result/FT01.txt", "w")
for result in result_list:
    f.write(result)
f.close()
